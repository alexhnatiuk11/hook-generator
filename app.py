import io
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from core import ANGLES, generate_variants, log_generation, to_combined_rows

load_dotenv()

st.set_page_config(page_title="SockLock Modification Generator", layout="wide")
st.title("SockLock Modification Generator")

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    st.error("ANTHROPIC_API_KEY not found. Add it to your .env file.")
    st.stop()

st.subheader("1. Winning script")
script_file = st.file_uploader("Upload a .txt file (optional)", type=["txt"])
script_text = st.text_area(
    "Or paste the script text here",
    height=200,
    value=script_file.read().decode("utf-8") if script_file else "",
)

st.subheader("2. Tested hooks library (optional)")
tested_file = st.file_uploader(
    "CSV with columns: hook, angle, status", type=["csv"], key="tested_csv"
)
tested_text = st.text_area(
    "Or paste CSV text here (columns: hook, angle, status)",
    height=150,
    value=tested_file.read().decode("utf-8") if tested_file else "",
)
tested_rows = None
if tested_text.strip():
    df_tested = pd.read_csv(io.StringIO(tested_text))
    st.dataframe(df_tested, use_container_width=True)
    tested_rows = df_tested.to_dict(orient="records")

st.subheader("3. Generation settings")
selected_angles = st.multiselect("Angles", ANGLES, default=[])
n_variants = st.slider("Variants per category (per angle)", 1, 15, 1)

if st.button("Generate", type="primary"):
    if not script_text.strip():
        st.warning("Paste or upload a winning script.")
    elif not selected_angles:
        st.warning("Pick at least one angle.")
    else:
        with st.spinner("Generating variants..."):
            try:
                variants_by_angle = generate_variants(
                    script=script_text,
                    angles=selected_angles,
                    n=n_variants,
                    api_key=api_key,
                    tested_rows=tested_rows,
                )
                log_generation(script_text, selected_angles, n_variants)

                rows = to_combined_rows(variants_by_angle, tested_rows=tested_rows)
                df_result = pd.DataFrame(rows)
                modifications_count = (df_result["angle"] != "").sum()
                st.success(f"Generated {modifications_count} ready-to-use modifications.")
                df_display = df_result.copy()
                df_display["variant"] = df_display["variant"].str.replace(
                    "\n", "<br>", regex=False
                )
                st.markdown(
                    """
                    <style>
                    table td { white-space: normal !important; text-align: left !important; }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown(
                    df_display.to_html(escape=False, index=False),
                    unsafe_allow_html=True,
                )

                csv_buffer = io.StringIO()
                df_result.to_csv(csv_buffer, index=False)
                st.download_button(
                    "Download CSV",
                    data=csv_buffer.getvalue(),
                    file_name="creative_variants.csv",
                    mime="text/csv",
                )

                st.caption(
                    "Estimate: one modification takes ~2h with the generator instead of "
                    "~3h (~1h saved per modification)."
                )
            except ValueError as e:
                st.error(str(e))
