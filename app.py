from __future__ import annotations
import os
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from sqlalchemy import Column, Float, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ==========================================
# НАСТРОЙКИ БД (как у вас, только с полным путём)
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "daily_routine.db")

try:
    DB_URL = st.secrets["database_url"]
except Exception:
    DB_URL = f"sqlite:///{DB_PATH}"

connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=connect_args)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# ==========================================
# МОДЕЛИ ДАННЫХ
# ==========================================
@dataclass
class DailyRecord:
    day: str
    sleep_hours: float
    physical_hours: float
    mental_hours: float
    notes: str = ""

class RecordDB(Base):
    __tablename__ = "daily_records"
    day = Column(String, primary_key=True)
    sleep_hours = Column(Float, nullable=False)
    physical_hours = Column(Float, nullable=False)
    mental_hours = Column(Float, nullable=False)
    notes = Column(Text, default="")

class EventDB(Base):
    __tablename__ = "events"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    event_date = Column(String, nullable=False)  # YYYY-MM-DD
    start_time = Column(String, nullable=False)  # HH:MM
    end_time = Column(String, nullable=False)    # HH:MM
    complexity = Column(String, default="medium") # low / medium / high

Base.metadata.create_all(engine)

# ==========================================
# РАБОТА С БД
# ==========================================
def load_records() -> List[DailyRecord]:
    session = Session()
    try:
        rows = session.query(RecordDB).order_by(RecordDB.day).all()
        return [DailyRecord(day=r.day, sleep_hours=r.sleep_hours,
                            physical_hours=r.physical_hours,
                            mental_hours=r.mental_hours,
                            notes=r.notes or "") for r in rows]
    finally:
        session.close()

def upsert_record(rec: DailyRecord) -> None:
    session = Session()
    try:
        existing = session.get(RecordDB, rec.day)
        if existing:
            existing.sleep_hours = rec.sleep_hours
            existing.physical_hours = rec.physical_hours
            existing.mental_hours = rec.mental_hours
            existing.notes = rec.notes
        else:
            session.add(RecordDB(**asdict(rec)))
        session.commit()
    finally:
        session.close()

def load_events(day: str) -> List[dict]:
    session = Session()
    try:
        rows = session.query(EventDB).filter(EventDB.event_date == day).all()
        return [{"id": r.id, "title": r.title, "date": r.event_date,
                 "start": r.start_time, "end": r.end_time,
                 "complexity": r.complexity} for r in rows]
    finally:
        session.close()

def save_event(event: dict) -> None:
    session = Session()
    try:
        existing = session.get(EventDB, event["id"])
        if existing:
            existing.title = event["title"]
            existing.event_date = event["date"]
            existing.start_time = event["start"]
            existing.end_time = event["end"]
            existing.complexity = event["complexity"]
        else:
            session.add(EventDB(**event))
        session.commit()
    finally:
        session.close()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ АНАЛИТИКИ
# ==========================================
def ensure_week(records: List[DailyRecord]) -> List[DailyRecord]:
    today = date.today()
    week_ago = today - timedelta(days=6)
    week_records = []
    for r in records:
        try:
            rec_date = datetime.strptime(r.day, "%Y-%m-%d").date()
            if week_ago <= rec_date <= today:
                week_records.append(r)
        except ValueError:
            continue
    week_records.sort(key=lambda x: x.day)
    return week_records

def weekly_stats(week_records: List[DailyRecord]) -> dict:
    if not week_records:
        return {"avg_physical": 0, "avg_mental": 0, "avg_sleep": 0}
    n = len(week_records)
    return {
        "avg_physical": sum(r.physical_hours for r in week_records) / n,
        "avg_mental": sum(r.mental_hours for r in week_records) / n,
        "avg_sleep": sum(r.sleep_hours for r in week_records) / n,
    }

# ==========================================
# ЛОГИКА ДЛЯ ФУНКЦИЙ ИЗ КОНЦЕПЦИИ
# ==========================================
def get_sleep_recommendations(wake_time: time) -> List[str]:
    """Возвращает 4 лучших времени отхода ко сну на основе 90-минутных циклов."""
    base = datetime.combine(date.today(), wake_time)
    recommendations = []
    for cycles in [6, 5, 4]:
        fall_asleep = base - timedelta(minutes=15) - timedelta(minutes=90 * cycles)
        recommendations.append(fall_asleep.strftime("%H:%M"))
    return recommendations

def get_energy_advice(avg_sleep: float) -> str:
    if avg_sleep >= 7.5:
        return "🟢 Высокий уровень энергии. Идеальное время для сложных задач."
    elif avg_sleep >= 6.0:
        return "🟡 Средний уровень энергии. Чередуйте сложные и легкие задачи."
    else:
        return "🔴 Низкий уровень энергии. Сфокусируйтесь на рутине и коротких перерывах."

def check_reminders(records: List[DailyRecord], events: List[dict]) -> List[str]:
    """Проверяет, не пора ли показать напоминание (упрощённая имитация)."""
    reminders = []
    now = datetime.now()
    current_time = now.time()

    # Напоминание о подготовке ко сну (если сейчас вечер и сон < 7ч)
    if now.hour >= 21 and records:
        last = records[-1]
        if last.sleep_hours < 7.0 and current_time >= time(21, 0):
            reminders.append("🌙 Пора готовиться ко сну: завтра будет продуктивнее!")

    # Напоминание о ближайшем событии
    for ev in events:
        try:
            ev_start = datetime.combine(now.date(), datetime.strptime(ev["start"], "%H:%M").time())
            delta = (ev_start - now).total_seconds() / 60
            if 0 < delta <= 15:
                reminders.append(f"⏰ Скоро начнётся «{ev['title']}» (через {int(delta)} мин.)")
        except Exception:
            continue
    return reminders

# ==========================================
# ИНТЕРФЕЙС
# ==========================================
st.set_page_config(page_title="Daily Routine — умный трекер", page_icon="⏰", layout="wide")
st.title("⏰ Daily Routine — умный трекер сна и расписания")
st.caption("Сервис, который строит ваш день вокруг фаз сна, а не наоборот.")

if "records" not in st.session_state:
    st.session_state.records = load_records()

# Боковая панель с быстрыми напоминаниями
with st.sidebar:
    st.header("🔔 Напоминания")
    today_str = date.today().strftime("%Y-%m-%d")
    events_today = load_events(today_str)
    reminders = check_reminders(st.session_state.records, events_today)
    if reminders:
        for msg in reminders:
            st.toast(msg, icon="🔔")[reference:4]
            st.warning(msg)
    else:
        st.info("Пока нет активных напоминаний. Добавьте события в планировщик.")

# Создаём вкладки
tab1, tab2, tab3, tab4 = st.tabs(["📝 Дневник", "📊 Аналитика", "🌙 Калькулятор сна", "📅 Планировщик"])

# ==========================================
# ВКЛАДКА 1: ДНЕВНИК
# ==========================================
with tab1:
    st.header("Ежедневная запись")
    with st.form("record_form"):
        day = st.date_input("Дата", value=date.today())
        sleep_hours = st.number_input("Часы сна (прошлой ночью)", 0.0, 24.0, 8.0, 0.5)
        physical_hours = st.number_input("Физическая активность (часы)", 0.0, 24.0, 1.0, 0.5)
        mental_hours = st.number_input("Умственная нагрузка (часы)", 0.0, 24.0, 6.0, 0.5)
        notes = st.text_area("Заметки (опционально)")
        submitted = st.form_submit_button("Сохранить запись")

        if submitted:
            new_record = DailyRecord(
                day=day.strftime("%Y-%m-%d"),
                sleep_hours=sleep_hours,
                physical_hours=physical_hours,
                mental_hours=mental_hours,
                notes=notes,
            )
            upsert_record(new_record)
            st.session_state.records = load_records()
            st.success("Запись успешно сохранена!")
            st.rerun()

# ==========================================
# ВКЛАДКА 2: АНАЛИТИКА (перенесено из старой версии)
# ==========================================
with tab2:
    st.header("Анализ сна и активности за неделю")
    wk = ensure_week(st.session_state.records)
    if wk:
        xs_labels = [datetime.strptime(r.day, "%Y-%m-%d").strftime("%a") for r in wk]
        ys = [r.sleep_hours for r in wk]
        x_idx = list(range(len(wk)))

        fig1 = plt.figure(figsize=(8, 4))
        plt.plot(x_idx, ys, marker="o", linestyle="-", color="b")
        plt.title("Часы сна по дням")
        plt.xlabel("Дни недели")
        plt.ylabel("Часы")
        plt.xticks(x_idx, xs_labels)
        plt.ylim(0, 12)
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.tight_layout()
        st.pyplot(fig1, clear_figure=True)

        s = weekly_stats(wk)
        phys_val = max(s["avg_physical"], 0.0001)
        ment_val = max(s["avg_mental"], 0.0001)

        fig2 = plt.figure(figsize=(5, 5))
        plt.pie([phys_val, ment_val],
                labels=["Физическая активность", "Умственная"],
                autopct="%1.1f%%", startangle=90,
                colors=["#4CAF50", "#2196F3"])
        plt.title("Среднее распределение активности")
        plt.tight_layout()
        st.pyplot(fig2, clear_figure=True)

        st.info(f"Средний сон за неделю: **{s['avg_sleep']:.1f} ч.**")
        st.success(get_energy_advice(s['avg_sleep']))
    else:
        st.warning("Пока нет данных за последние 7 дней. Добавьте первую запись!")

# ==========================================
# ВКЛАДКА 3: КАЛЬКУЛЯТОР СНА
# ==========================================
with tab3:
    st.header("🌙 Калькулятор циклов сна")
    st.write("Укажите, во сколько вы хотите проснуться, и мы рассчитаем, когда лучше лечь спать.")
    wake_time = st.time_input("Время пробуждения", value=time(7, 0))
    if st.button("Рассчитать время отхода ко сну"):
        recs = get_sleep_recommendations(wake_time)
        st.subheader("Рекомендуемое время отхода ко сну:")
        for i, rec in enumerate(recs, start=1):
            st.write(f"**Цикл {7 - i}** (≈ {90 * (7 - i)} мин. сна) → {rec}")
        st.caption("Расчёт основан на стандартном 90-минутном цикле сна и 15 минутах на засыпание.")
    st.info("💡 Совет: спите не менее 7–8 часов, чтобы поддерживать когнитивные функции.")

# ==========================================
# ВКЛАДКА 4: ПЛАНИРОВЩИК
# ==========================================
with tab4:
    st.header("📅 Планировщик и рекомендации")
    st.subheader("Ближайшие события")
    today_str = date.today().strftime("%Y-%m-%d")
    events = load_events(today_str)

    if events:
        df_events = pd.DataFrame(events)[["start", "end", "title", "complexity"]]
        df_events.columns = ["Начало", "Конец", "Событие", "Сложность"]
        st.table(df_events)
    else:
        st.info("На сегодня событий нет.")

    st.divider()
    st.subheader("Добавить событие")
    with st.form("event_form"):
        title = st.text_input("Название события")
        ev_date = st.date_input("Дата", value=date.today())
        start_t = st.time_input("Начало", value=time(9, 0))
        end_t = st.time_input("Конец", value=time(10, 0))
        complexity = st.selectbox("Сложность задачи", ["low", "medium", "high"])
        add_event = st.form_submit_button("Сохранить событие")

        if add_event and title:
            ev_id = f"{ev_date}_{start_t}_{title.replace(' ', '_')[:20]}"
            event = {
                "id": ev_id,
                "title": title,
                "date": ev_date.strftime("%Y-%m-%d"),
                "start": start_t.strftime("%H:%M"),
                "end": end_t.strftime("%H:%M"),
                "complexity": complexity,
            }
            save_event(event)
            st.success("Событие добавлено!")
            st.rerun()

    st.divider()
    st.subheader("💡 Рекомендация по дню")
    wk = ensure_week(st.session_state.records)
    if wk:
        last_sleep = wk[-1].sleep_hours
        st.write(get_energy_advice(last_sleep))
        if last_sleep < 7:
            st.warning("⚠️ Сегодня лучше избегать сложных задач и сделать перерыв.")
        else:
            st.success("✅ Хороший сон — отличное время для сложных проектов!")