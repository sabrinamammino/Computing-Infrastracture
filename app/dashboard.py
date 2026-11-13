"""Dashboard: AI model pricing, September 2023 to September 2026.

Reads the ai_models table (written by the loader) and shows the answers to
five SQL queries: three charts and two tables.
"""
import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

st.set_page_config(page_title="AI model pricing", layout="wide")

env = os.environ


@st.cache_resource
def get_engine():
    # The host is "db": the service name in docker-compose.yml, not "localhost".
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=env["POSTGRES_USER"],
            password=env["POSTGRES_PASSWORD"],
            host="db",
            port=5432,
            database=env["POSTGRES_DB"],
        )
    )


@st.cache_data(ttl=600)
def run_query(sql: str) -> pd.DataFrame:
    """Run one SQL query and return the result as a table (cached for 10 minutes)."""
    with get_engine().connect() as conn:
        df = pd.read_sql(text(sql), conn)
    # PostgreSQL returns ROUND(...) results as Decimal objects; charts need floats.
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
    return df


def show_sql(sql: str):
    with st.expander("Show the SQL"):
        st.code(sql.strip(), language="sql")


# ---------------------------------------------------------------------------
# The five queries (the same ones as in sql/queries.sql: Q4, Q6, Q7, Q2, Q3)
# ---------------------------------------------------------------------------
Q4_MEDIAN_PRICE = """
SELECT date_trunc('quarter', week_start)::date AS quarter,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY input_price_per_1m_tokens))::numeric, 3)  AS median_input_usd,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY output_price_per_1m_tokens))::numeric, 3) AS median_output_usd
FROM ai_models
WHERE mode = 'chat'
  AND input_price_per_1m_tokens  > 0
  AND output_price_per_1m_tokens > 0
GROUP BY 1
ORDER BY 1
"""

Q6_CUTS_VS_RISES = """
WITH weekly AS (
    SELECT week_start,
           input_price_per_1m_tokens AS price,
           LAG(input_price_per_1m_tokens) OVER (PARTITION BY model_id ORDER BY week_start) AS prev_price
    FROM ai_models
    WHERE mode = 'chat'
)
SELECT date_trunc('quarter', week_start)::date AS quarter,
       ROUND(1000.0 * COUNT(*) FILTER (WHERE price < prev_price) / COUNT(*), 2) AS cuts_per_1000,
       ROUND(1000.0 * COUNT(*) FILTER (WHERE price > prev_price) / COUNT(*), 2) AS rises_per_1000
FROM weekly
WHERE prev_price > 0 AND price > 0
GROUP BY 1
ORDER BY 1
"""

Q7_CAPABILITIES = """
SELECT date_trunc('quarter', week_start)::date AS quarter,
       ROUND(100 * AVG(supports_reasoning::int),        1) AS pct_reasoning,
       ROUND(100 * AVG(supports_vision::int),           1) AS pct_vision,
       ROUND(100 * AVG(supports_function_calling::int), 1) AS pct_function_calling,
       ROUND(100 * AVG(supports_prompt_caching::int),   1) AS pct_prompt_caching
FROM ai_models
WHERE mode = 'chat'
GROUP BY 1
HAVING COUNT(supports_reasoning) > 0
ORDER BY 1
"""

Q2_CHEAPEST_CAPABLE = """
SELECT model_name,
       provider,
       developer,
       input_price_per_1m_tokens  AS input_usd,
       output_price_per_1m_tokens AS output_usd,
       ROUND(((3 * input_price_per_1m_tokens + output_price_per_1m_tokens) / 4)::numeric, 3) AS blended_usd,
       max_input_tokens
FROM ai_models
WHERE week_start = (SELECT MAX(week_start) FROM ai_models)
  AND mode = 'chat'
  AND supports_vision
  AND supports_function_calling
  AND input_price_per_1m_tokens  > 0
  AND output_price_per_1m_tokens > 0
ORDER BY blended_usd, model_name
LIMIT 10
"""

Q3_PROVIDER_SPREAD = """
SELECT model_name,
       COUNT(DISTINCT provider)                              AS providers,
       MIN(input_price_per_1m_tokens)                        AS cheapest_input_usd,
       MAX(input_price_per_1m_tokens)                        AS priciest_input_usd,
       ROUND((MAX(input_price_per_1m_tokens)
              / MIN(input_price_per_1m_tokens))::numeric, 1) AS times_more_expensive
FROM ai_models
WHERE week_start = (SELECT MAX(week_start) FROM ai_models)
  AND mode = 'chat'
  AND input_price_per_1m_tokens > 0
GROUP BY model_name
HAVING COUNT(DISTINCT provider) >= 5
ORDER BY times_more_expensive DESC
LIMIT 10
"""

OVERVIEW = """
SELECT MIN(week_start) AS first_week,
       MAX(week_start) AS last_week,
       COUNT(*)        AS rows_loaded,
       COUNT(DISTINCT model_id) AS listings,
       COUNT(DISTINCT developer) AS developers
FROM ai_models
"""

# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
st.title("How have AI model prices and abilities changed?")

try:
    overview = run_query(OVERVIEW).iloc[0]
except Exception:
    st.error(
        "The table ai_models was not found. Did the loader finish? "
        "Run `docker compose logs loader` to see what happened."
    )
    st.stop()

st.caption(
    f"Weekly snapshots of {int(overview.listings):,} model listings from "
    f"{int(overview.developers)} developers, {overview.first_week} to {overview.last_week} "
    f"({int(overview.rows_loaded):,} rows)."
)

st.header("1. Are typical prices falling?")
st.write("Median price in US dollars per 1 million tokens, chat models, per quarter.")
q4 = run_query(Q4_MEDIAN_PRICE)
q4["quarter"] = pd.to_datetime(q4["quarter"])
st.line_chart(q4, x="quarter", y=["median_input_usd", "median_output_usd"])
st.caption(
    "The median also moves because the mix of models changes (more cheap open "
    "models appear). Chart 2 compares each model with its own earlier price."
)
show_sql(Q4_MEDIAN_PRICE)

st.header("2. Do price cuts outnumber price rises?")
st.write(
    "Share of week-to-week price changes, per 1,000 comparisons: how often a "
    "model's input price went down or up compared with its previous week."
)
q6 = run_query(Q6_CUTS_VS_RISES)
q6["quarter"] = pd.to_datetime(q6["quarter"])
st.line_chart(q6, x="quarter", y=["cuts_per_1000", "rises_per_1000"])
show_sql(Q6_CUTS_VS_RISES)

st.header("3. Which abilities are becoming standard?")
st.write("Share of chat models that support each ability, per quarter.")
q7 = run_query(Q7_CAPABILITIES)
q7["quarter"] = pd.to_datetime(q7["quarter"])
st.line_chart(
    q7,
    x="quarter",
    y=["pct_reasoning", "pct_vision", "pct_function_calling", "pct_prompt_caching"],
)
st.caption(
    "Caution: the ability flags only exist for models still listed in 2026, "
    "so older quarters describe survivors only."
)
show_sql(Q7_CAPABILITIES)

st.header("4. Cheapest capable models now")
st.write(
    "Chat models that can read images and call functions, in the latest "
    "week, cheapest first. Blended price assumes 3 input tokens per output token."
)
st.dataframe(run_query(Q2_CHEAPEST_CAPABLE), hide_index=True, width="stretch")
show_sql(Q2_CHEAPEST_CAPABLE)

st.header("5. The provider changes the price")
st.write(
    "The same model sold by 5 or more providers: how many times more "
    "expensive is the priciest provider than the cheapest?"
)
st.dataframe(run_query(Q3_PROVIDER_SPREAD), hide_index=True, width="stretch")
show_sql(Q3_PROVIDER_SPREAD)
