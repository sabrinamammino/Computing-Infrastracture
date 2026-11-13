-- sql/queries.sql: the queries behind the dashboard (app/dashboard.py).
-- Table ai_models: one row per model, provider and week. Prices are in US
-- dollars per 1 million tokens.
--
-- To run one: docker compose exec db psql -U team -d project
--
-- Notes on the data
--  * It is a weekly snapshot, so for current figures we filter to the latest
--    week in the data (2026-09-28).
--  * We leave out prices of 0 (free or self-hosted models) in price statistics.
--  * supports_* and developer_country are empty for models that are not in the
--    2026 list.
--  * The loader stores the date columns as DATE, which date_trunc() needs.

-- Query 1. Median price per quarter, chat models.
-- We use the median because a few very expensive models distort the average.
SELECT date_trunc('quarter', week_start)::date AS quarter,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY input_price_per_1m_tokens))::numeric, 3)  AS median_input_usd,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY output_price_per_1m_tokens))::numeric, 3) AS median_output_usd
FROM ai_models
WHERE mode = 'chat'
  AND input_price_per_1m_tokens  > 0
  AND output_price_per_1m_tokens > 0
GROUP BY 1
ORDER BY 1;

-- Query 2. How often a model's input price goes down or up compared with
-- its previous week, per 1,000 comparisons.
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
ORDER BY 1;

-- Query 3. Share of chat models that support each ability, per quarter.
-- The ability flags only exist for models still listed in 2026, so older
-- quarters describe survivors only.
SELECT date_trunc('quarter', week_start)::date AS quarter,
       ROUND(100 * AVG(supports_reasoning::int),        1) AS pct_reasoning,
       ROUND(100 * AVG(supports_vision::int),           1) AS pct_vision,
       ROUND(100 * AVG(supports_function_calling::int), 1) AS pct_function_calling,
       ROUND(100 * AVG(supports_prompt_caching::int),   1) AS pct_prompt_caching
FROM ai_models
WHERE mode = 'chat'
GROUP BY 1
HAVING COUNT(supports_reasoning) > 0
ORDER BY 1;

-- Query 4. The 10 cheapest chat models in the latest week that support
-- vision and function calling. Blended price = 3 input tokens per 1 output token.
-- This is our main query for the index measurement (see the end of the file).
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
LIMIT 10;

-- Query 5. Models sold by 5 or more providers: how many times more expensive
-- the priciest provider is than the cheapest.
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
LIMIT 10;

-- Query 6. Overview for the caption at the top of the dashboard.
SELECT MIN(week_start) AS first_week,
       MAX(week_start) AS last_week,
       COUNT(*)        AS rows_loaded,
       COUNT(DISTINCT model_id) AS listings,
       COUNT(DISTINCT developer) AS developers
FROM ai_models;



-- Index measurement (README): we time Query 4 with EXPLAIN ANALYZE, 3 runs,
-- and average them. Then:
--     CREATE INDEX idx_ai_models_week ON ai_models (week_start);
--     ANALYZE ai_models;
-- We time it again, 3 runs, and average. To go back to no index:
--     DROP INDEX idx_ai_models_week;