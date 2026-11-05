import os
import psycopg2
import streamlit as st

conn = psycopg2.connect(
    host="db",
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
cur = conn.cursor()
cur.execute("SELECT id, message FROM hello ORDER BY id")

st.title("Placeholder dashboard")
st.write("Rows the loader wrote into the database:")
st.table(cur.fetchall())