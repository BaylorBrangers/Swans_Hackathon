"""Streamlit page for the demo lost-income estimator."""

import streamlit as st

from lost_income import render_lost_income_view


st.set_page_config(page_title="Lost Income Estimate", layout="wide")
st.title("Lost Income Estimate")
render_lost_income_view()
