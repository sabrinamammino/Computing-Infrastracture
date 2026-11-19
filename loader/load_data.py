"""Loader: gets the AI models CSV, fixes the column types, writes it to PostgreSQL.

Runs once when `docker compose up` starts, then exits. The dashboard (app)
starts after it finishes.

Settings come from the .env file:
  POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB   database login
  DATA_FILE      name of the CSV inside the data/ folder (default ai_models_merged.csv)
  DATA_URL       where to download the CSV if it is not in data/ yet (optional)
  DATA_FRACTION  share of the data to load: 0.25, 0.5 or 1.0 (default 1.0)
"""
import os
import time
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.types import Date

env = os.environ

# The host is "db": the service name in docker-compose.yml, not "localhost".
engine = create_engine(
    URL.create(
        "postgresql+psycopg2",
        username=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        host="db",
        port=5432,
        database=env["POSTGRES_DB"],
    )
)

DATA_DIR = Path("/data")  # the data/ folder on your laptop, shared with this container
DATA_FILE = DATA_DIR / env.get("DATA_FILE", "ai_models_merged.csv")
DATA_URL = env.get("DATA_URL", "").strip()
FRACTION = float(env.get("DATA_FRACTION", "1.0"))

TABLE = "ai_models"
DATE_COLUMNS = ["week_start", "deprecation_date", "first_listed_week"]

total_start = time.perf_counter()

# 1. Get the file: use the copy in data/, or download it once.
t = time.perf_counter()
if DATA_FILE.exists():
    print(f"using local file {DATA_FILE.name} ({DATA_FILE.stat().st_size / 1e6:.1f} MB)")
elif DATA_URL:
    DATA_DIR.mkdir(exist_ok=True)
    print(f"downloading {DATA_URL}")
    with requests.get(DATA_URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(DATA_FILE, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"downloaded {DATA_FILE.stat().st_size / 1e6:.1f} MB")
else:
    raise SystemExit(
        f"{DATA_FILE.name} is not in the data/ folder and DATA_URL is empty. "
        "Put the CSV in data/ or set DATA_URL in .env."
    )
print(f"get file: {time.perf_counter() - t:.1f}s")

# 2. Read it.
t = time.perf_counter()
df = pd.read_csv(DATA_FILE, low_memory=False)
print(f"read csv: {len(df)} rows in {time.perf_counter() - t:.1f}s")

# 3. Fix the types. Without this the three date columns are stored as text
#    and date functions in SQL (date_trunc, date arithmetic) fail.
for col in DATE_COLUMNS:
    df[col] = pd.to_datetime(df[col]).dt.date

# 4. Optional smaller run for the measurements (25%, 50%, 100%).
#    Keeps a share of WHOLE MODELS, spread across the alphabet, so every
#    size still covers all weeks and most developers. df.head() would only
#    keep the models at the start of the alphabet.
if FRACTION < 1.0:
    keep = pd.util.hash_pandas_object(df["model_id"], index=False) % 100 < FRACTION * 100
    df = df[keep]
    print(f"DATA_FRACTION={FRACTION}: keeping {len(df)} rows")

# 5. Write to the database. "replace" rebuilds the table on every run.
t = time.perf_counter()
df.to_sql(
    TABLE,
    engine,
    if_exists="replace",
    index=False,
    chunksize=50_000,
    dtype={col: Date() for col in DATE_COLUMNS},
)
print(f"write to database: {len(df)} rows in {time.perf_counter() - t:.1f}s")

print(f"TOTAL: {time.perf_counter() - total_start:.1f}s")
print("loader finished")