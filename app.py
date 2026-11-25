from __future__ import annotations
import os

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st
from sqlalchemy import Column, Float, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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
# МОДЕЛИ
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


Base.metadata.create_all(engine)


# ==========================================
# ФУНКЦИИ РАБОТЫ С БД
# ==========================================
def load_records() -> List[DailyRecord]:
    session = Session()
    try:
        rows = session.query(RecordDB).order_by(RecordDB.day).all()
        return [
            DailyRecord(
                day=r.day,
                sleep_hours=r.sleep_hours,
                physical_hours=r.physical_hours,
                mental_hours=r.mental_hours,
                notes=r.notes or "",
            )
            for r in rows
        ]
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


# ==========================================
# АНАЛИТИКА
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
# ИНТЕРФЕЙС
# ==========================================
st.set_page_config(
    page_title="Daily routine and sleeping",
    page_icon="⏰",
    layout="centered",
)

if "records" not in st.session_state:
    st.session_state.records = load_records()

st.title("⏰ Daily routine and sleeping")
st.caption("Трекер вашего ежедневного распорядка и качества сна")

with st.form("record_form"):
    st.subheader("Ежедневная запись")
    day = st.date_input("Дата", value=date.today())
    sleep_hours = st.number_input(
        "Часы сна (прошлой ночью)", 0.0, 24.0, 8.0, 0.5
    )
    physical_hours = st.number_input(
        "Физическая активность сегодня (часы)", 0.0, 24.0, 1.0, 0.5
    )
    mental_hours = st.number_input(
        "Умственная нагрузка (часы)", 0.0, 24.0, 6.0, 0.5
    )
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

st.divider()
st.header("Анализ сна и активности за неделю")

wk = ensure_week(st.session_state.records)

if wk:
    xs_labels = [
        datetime.strptime(r.day, "%Y-%m-%d").strftime("%a") for r in wk
    ]
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
    plt.pie(
        [phys_val, ment_val],
        labels=["Физическая активность", "Умственная"],
        autopct="%1.1f%%",
        startangle=90,
        colors=["#4CAF50", "#2196F3"],
    )
    plt.title("Среднее распределение активности")
    plt.tight_layout()
    st.pyplot(fig2, clear_figure=True)

    st.info(f"Средний сон за неделю: **{s['avg_sleep']:.1f} ч.**")
else:
    st.warning("Пока нет данных за последние 7 дней. Добавьте первую запись!")