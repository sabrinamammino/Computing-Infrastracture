import os
import psycopg2

conn = psycopg2.connect(
    host="db",
    port=5432,
    dbname=os.environ["POSTGRES_DB"],
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS hello (id SERIAL PRIMARY KEY, message TEXT)")
cur.execute("INSERT INTO hello (message) VALUES (%s)", ("the loader ran",))
conn.commit()
print("loader finished")