import io
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core import ANGLES, generate_variants, to_combined_rows

load_dotenv()

st.set_page_config(page_title="Hook Generator", layout="wide")
st.title("Hook Generator — SockLock creative modifications")

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    st.error("ANTHROPIC_API_KEY не знайдено. Додай його в .env файл.")
    st.stop()

st.subheader("1. Скрипт переможця")
script_file = st.file_uploader("Завантажити .txt файл (опційно)", type=["txt"])
script_text = st.text_area(
    "Або встав текст скрипта сюди",
    height=200,
    value=script_file.read().decode("utf-8") if script_file else "",
)

st.subheader("2. Бібліотека протестованих хуків (опційно)")
tested_file = st.file_uploader(
    "CSV з колонками: hook, angle, status", type=["csv"], key="tested_csv"
)
tested_text = st.text_area(
    "Або встав CSV текстом сюди (колонки: hook, angle, status)",
    height=150,
    value=tested_file.read().decode("utf-8") if tested_file else "",
)
tested_rows = None
if tested_text.strip():
    df_tested = pd.read_csv(io.StringIO(tested_text))
    st.dataframe(df_tested, use_container_width=True)
    tested_rows = df_tested.to_dict(orient="records")

st.subheader("3. Налаштування генерації")
selected_angles = st.multiselect("Кути подачі", ANGLES, default=ANGLES)
n_variants = st.slider("Кількість варіантів на категорію (на кут)", 1, 15, 5)

if st.button("Згенерувати", type="primary"):
    if not script_text.strip():
        st.warning("Встав або завантаж скрипт переможця.")
    elif not selected_angles:
        st.warning("Обери хоча б один кут подачі.")
    else:
        with st.spinner("Генерую варіанти..."):
            try:
                variants_by_angle = generate_variants(
                    script=script_text,
                    angles=selected_angles,
                    n=n_variants,
                    api_key=api_key,
                    tested_rows=tested_rows,
                )
                rows = to_combined_rows(variants_by_angle)
                df_result = pd.DataFrame(rows)
                modifications_count = (df_result["angle"] != "").sum()
                st.success(f"Згенеровано {modifications_count} готових модифікацій.")
                st.dataframe(df_result, use_container_width=True)

                csv_buffer = io.StringIO()
                df_result.to_csv(csv_buffer, index=False)
                st.download_button(
                    "Скачати CSV",
                    data=csv_buffer.getvalue(),
                    file_name="creative_variants.csv",
                    mime="text/csv",
                )

                st.caption(
                    "Оцінка: одна модифікація з генератором ~2 год замість ~3 год "
                    "(економія ~1 год на модифікацію)."
                )
            except ValueError as e:
                st.error(str(e))
