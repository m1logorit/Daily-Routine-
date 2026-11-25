from __future__ import annotations
import os
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import List
import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from sqlalchemy import Column, Float, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Импорты для красивого дизайна
from streamlit_calendar import calendar
from streamlit_lottie import st_lottie

# ==========================================
# НАСТРОЙКИ СТРАНИЦЫ И СТИЛИ (CSS)
# ==========================================
st.set_page_config(page_title="Daily Routine", page_icon="⏰", layout="wide")

# Внедряем кастомный CSS для красоты
st.markdown("""
<style>
    /* Красивые карточки */
    div[data-testid="stExpander"], div[data-testid="stForm"] {
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        border: 1px solid #f0f2f6;
        padding: 15px;
    }
    /* Кнопки */
    .stButton>button {
        border-radius: 20px;
        background-image: linear-gradient(to right, #4CAF50, #2196F3);
        color: white;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: scale(1.05);
        box-shadow: 0 5px 15px rgba(33, 150, 243, 0.4);
    }
    /* Заголовки */
    h1, h2, h3 {
        font-family: 'Helvetica Neue', sans-serif;
    }
    /* Красивая плашка (Hero-секция) */
    .hero-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 40px;
        border-radius: 20px;
        color: white;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.15);
    }
    .hero-title { font-size: 2.5rem; font-weight: bold; margin-bottom: 10px; }
    .hero-subtitle { font-size: 1.2rem; opacity: 0.9; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# НАСТРОЙКИ БД
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
    event_date = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    complexity = Column(String, default="medium")

Base.metadata.create_all(engine)

# ==========================================
# ФУНКЦИИ РАБОТЫ С БД
# ==========================================
def load_records() -> List[DailyRecord]:
    session = Session()
    try:
        rows = session.query(RecordDB).order_by(RecordDB.day).all()
        return [DailyRecord(day=r.day, sleep_hours=r.sleep_hours, physical_hours=r.physical_hours,
                            mental_hours=r.mental_hours, notes=r.notes or "") for r in rows]
    finally:
        session.close()

def upsert_record(rec: DailyRecord) -> None:
    session = Session()
    try:
        existing = session.get(RecordDB, rec.day)
        if existing:
            existing.sleep_hours, existing.physical_hours = rec.sleep_hours, rec.physical_hours
            existing.mental_hours, existing.notes = rec.mental_hours, rec.notes
        else:
            session.add(RecordDB(**asdict(rec)))
        session.commit()
    finally:
        session.close()

def load_all_events() -> List[dict]:
    session = Session()
    try:
        rows = session.query(EventDB).all()
        return [{"id": r.id, "title": r.title, "date": r.event_date, "start": r.start_time,
                 "end": r.end_time, "complexity": r.complexity} for r in rows]
    finally:
        session.close()

def save_event(event: dict) -> None:
    session = Session()
    try:
        session.add(EventDB(**event))
        session.commit()
    finally:
        session.close()

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================
def load_lottieurl(url: str):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()

def ensure_week(records: List[DailyRecord]) -> List[DailyRecord]:
    today = date.today()
    week_ago = today - timedelta(days=6)
    week_records = [r for r in records if week_ago <= datetime.strptime(r.day, "%Y-%m-%d").date() <= today]
    week_records.sort(key=lambda x: x.day)
    return week_records

# ==========================================
# ИНТЕРФЕЙС
# ==========================================
if "records" not in st.session_state:
    st.session_state.records = load_records()

# 1. КРАСИВАЯ ГЛАВНАЯ ПЛАШКА (Hero)
st.markdown("""
<div class="hero-container">
    <div class="hero-title">⏰ Daily Routine</div>
    <div class="hero-subtitle">Умный трекер, который строит ваш день вокруг фаз сна.<br>Сохраняйте баланс между работой, отдыхом и здоровьем.</div>
</div>
""", unsafe_allow_html=True)

# 2. ВКЛАДКИ
tab_home, tab_diary, tab_calendar, tab_alarm, tab_stats = st.tabs([
    "🏠 Главная", "📝 Дневник", "📅 Календарь", "⏰ Будильник", "📊 Аналитика"
])

# --- ВКЛАДКА: ГЛАВНАЯ ---
with tab_home:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Почему это важно?")
        st.write("""
        Современный ритм жизни часто приводит к дефициту сна. Мы работаем до ночи и встаем разбитыми, 
        теряя продуктивность. **Daily Routine** помогает управлять расписанием, а не просто констатировать недосып.
        
        **Наши фишки:**
        *   🌙 Расчет идеального времени сна по циклам.
        *   📅 Умный календарь задач.
        *   📊 Анализ вашей энергии.
        """)
    with col2:
        # Загружаем милую анимацию сна
        lottie_sleep = load_lottieurl("https://assets5.lottiefiles.com/packages/lf20_5tkzkblw.json")
        if lottie_sleep:
            st_lottie(lottie_sleep, height=250, key="sleep")

# --- ВКЛАДКА: ДНЕВНИК ---
with tab_diary:
    st.subheader("📝 Как прошел ваш день?")
    with st.form("record_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            day = st.date_input("Дата", value=date.today())
            sleep_hours = st.number_input("Часы сна", 0.0, 24.0, 8.0, 0.5)
        with col2:
            physical_hours = st.number_input("Физическая активность (ч)", 0.0, 24.0, 1.0, 0.5)
            mental_hours = st.number_input("Умственная нагрузка (ч)", 0.0, 24.0, 6.0, 0.5)
        with col3:
            notes = st.text_area("Заметки", placeholder="Как ваше самочувствие?")
            st.write("")
            st.write("")
            submitted = st.form_submit_button("Сохранить запись", use_container_width=True)

        if submitted:
            new_record = DailyRecord(day=day.strftime("%Y-%m-%d"), sleep_hours=sleep_hours,
                                     physical_hours=physical_hours, mental_hours=mental_hours, notes=notes)
            upsert_record(new_record)
            st.session_state.records = load_records()
            st.success("✅ Запись сохранена!")
            st.rerun()

# --- ВКЛАДКА: КАЛЕНДАРЬ ---
with tab_calendar:
    st.subheader("📅 Ваш календарь событий")
    
    # Форма добавления события
    with st.expander("➕ Добавить новое событие"):
        with st.form("new_event"):
            ev_title = st.text_input("Название (например, 'Созвон с командой')")
            ev_date = st.date_input("Дата события", value=date.today())
            col_t1, col_t2 = st.columns(2)
            with col_t1: ev_start = st.time_input("Начало", value=time(10, 0))
            with col_t2: ev_end = st.time_input("Конец", value=time(11, 0))
            if st.form_submit_button("Добавить в календарь"):
                if ev_title:
                    ev_id = f"{ev_date}_{ev_start}_{ev_title[:10]}".replace(" ", "_")
                    save_event({
                        "id": ev_id, "title": ev_title, "date": ev_date.strftime("%Y-%m-%d"),
                        "start": ev_start.strftime("%H:%M"), "end": ev_end.strftime("%H:%M"), "complexity": "medium"
                    })
                    st.success("Событие добавлено!")
                    st.rerun()
                else:
                    st.error("Введите название события")

    # Отрисовка календаря
    events_db = load_all_events()
    calendar_events = []
    for e in events_db:
        calendar_events.append({
            "title": e["title"],
            "start": f"{e['date']}T{e['start']}:00",
            "end": f"{e['date']}T{e['end']}:00",
            "backgroundColor": "#2196F3" if e["complexity"] == "medium" else "#4CAF50",
            "borderColor": "#2196F3",
        })

    calendar_options = {
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "dayGridMonth",
    }
    
    calendar(events=calendar_events, options=calendar_options, custom_css="""
        .fc-event { border-radius: 5px; font-size: 0.85em; }
    """)

# --- ВКЛАДКА: БУДИЛЬНИК ---
with tab_alarm:
    st.subheader("⏰ Умный калькулятор сна")
    st.write("Сон состоит из циклов по 90 минут. Чтобы проснуться бодрым, нужно просыпаться в конце цикла.")
    
    col_a, col_b = st.columns([1, 1])
    with col_a:
        wake_time = st.time_input("Я хочу проснуться в:", value=time(7, 0))
        st.write("")
        if st.button("Рассчитать время сна", use_container_width=True):
            base = datetime.combine(date.today(), wake_time)
            st.success("Вам нужно лечь спать в один из моментов:")
            for cycles in [6, 5, 4]:
                fall_asleep = base - timedelta(minutes=15) - timedelta(minutes=90 * cycles)
                st.info(f"**{fall_asleep.strftime('%H:%M')}** (сон {1.5 * cycles} часа)")
                
    with col_b:
        # Анимация будильника
        lottie_alarm = load_lottieurl("https://assets10.lottiefiles.com/packages/lf20_ksubyjmy.json")
        if lottie_alarm:
            st_lottie(lottie_alarm, height=250, key="alarm")

# --- ВКЛАДКА: АНАЛИТИКА ---
with tab_stats:
    st.subheader("📊 Анализ ваших показателей")
    wk = ensure_week(st.session_state.records)
    
    if wk:
        df = pd.DataFrame([asdict(r) for r in wk])
        df['day'] = pd.to_datetime(df['day']).dt.strftime('%d %b')
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Часы сна**")
            st.bar_chart(df.set_index('day')['sleep_hours'], color="#4CAF50")
        with col2:
            st.write("**Умственная и физическая нагрузка**")
            st.line_chart(df.set_index('day')[['physical_hours', 'mental_hours']], color=["#FF9800", "#2196F3"])
            
        avg_sleep = df['sleep_hours'].mean()
        if avg_sleep >= 7.5:
            st.success(f"🟢 Ваш средний сон: {avg_sleep:.1f} ч. Отличный результат! Вы полны энергии.")
        elif avg_sleep >= 6.0:
            st.warning(f"🟡 Ваш средний сон: {avg_sleep:.1f} ч. Старайтесь спать чуть больше.")
        else:
            st.error(f"🔴 Ваш средний сон: {avg_sleep:.1f} ч. Осторожно, накапливается усталость!")
    else:
        st.info("Добавьте записи в Дневник, чтобы увидеть графики.")