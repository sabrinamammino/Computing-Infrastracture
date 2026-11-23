# Computing-Infrastracture
# AI model prices and abilities, 2023 to 2026
## 1. Question and dataset
How have AI model prices and abilities changed? Data: weekly snapshots of 4,297
model listings from 43 developers, 167,787 rows, from Kaggle
(author, link and licence: see the Kaggle page).
## 2. Architecture
```mermaid
flowchart LR
K[Kaggle dataset] -->|download and clean| L[loader container]
L -->|writes table ai_models| D[(db container: PostgreSQL)]
D -->|SQL queries| A[app container: Streamlit]
A -->|port 8501| B[Browser]
```
db: PostgreSQL 16. loader: downloads, cleans and loads the data, then exits.
app: Streamlit dashboard that runs the SQL queries.
## 3. How to run
1. Install Docker Desktop.
2. `git clone <repo url>` and open the folder.
3. Copy `.env.example` to `.env`.
4. `docker compose up --build`
5. Open http://localhost:8501

## 6. Measurements
### A. Time, memory and disk at 25%, 50% and 100%

| Data | Rows | Load time (s) avg of 3 | Memory (MiB) avg of 3 | Database size |
|---|---|---|---|---|
| 25% | 41,696 | 2.0 | 244.4 | 16 MB |
| 50% | 83,628 | 3.7 | 297.9 | 24 MB |
| 100% | 167,787 | 7.1 | 356.7 | 41 MB |

Memory is the highest value seen by `docker stats` (about one sample per second), so it is approximate.
Reading the CSV always takes 0.2 s because the loader reads the whole file before sampling; almost all
the load time is the database write, which grows linearly with the number of rows.

### B. Index test (100% data)

| Query 4 | Run 1 (ms) | Run 2 (ms) | Run 3 (ms) | Average (ms) |
|---|---|---|---|---|
| Without index | 31.85 | 35.76 | 32.65 | 33.42 |
| With index | 25.96 | 7.33 | 6.58 | 13.29 |

Yes: with an index on `week_start`, Query 4 went from 33.4 ms to 13.3 ms on average (about 2.5× faster),
and to about 7 ms (about 5× faster) once the index was cached, because Postgres no longer scans the whole
table and reads only the 3,500 rows of the latest week.