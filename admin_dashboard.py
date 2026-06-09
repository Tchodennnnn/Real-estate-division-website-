import streamlit as st
import pandas as pd
from db import get_connection

def dashboard():

    st.title("Admin Dashboard")

    conn = get_connection()

    query = """
    SELECT *
    FROM applications
    ORDER BY applied_at DESC
    """

    df = pd.read_sql(query, conn)

    st.dataframe(df)

    conn.close()