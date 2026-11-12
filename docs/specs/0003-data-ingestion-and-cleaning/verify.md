# Verify: data ingestion and cleaning pipeline · spec 0003 · updated 2026-11-12

_Steps derived from spec 0003 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## UI / manual

(None, this is a pure backend data pipeline feature)

## Commands

- [ ] `uv run python scripts/load_to_sql.py --rebuild` → populates 1,067,371 raw rows, 1,003,420 clean transactions, 4,732 products, 5,852 customers, and refreshes 5 tables in exports/ → AC-1, AC-8, AC-9
- [ ] `uv run python -c "from scripts.db import connect_db; conn = connect_db('retail.db'); print(conn.execute('SELECT COUNT(*) FROM dim_date').fetchone()[0])"` → returns 761 continuous days from 2009-12-01 to 2011-12-31 → AC-2
- [ ] `uv run python -c "from scripts.db import connect_db; conn = connect_db('retail.db'); print(conn.execute('SELECT COUNT(*) FROM raw_transactions').fetchone()[0])"` → returns 1,067,371 rows across both sheets → AC-1
- [ ] `uv run python -c "from scripts.db import connect_db; conn = connect_db('retail.db'); cur = conn.cursor(); print(cur.execute('SELECT remaining_rows, remaining_revenue FROM cleaning_audit ORDER BY step_order').fetchall())"` → validates sequential audit subtraction and arithmetic reconciliation → AC-7
- [ ] `uv run python -c "from scripts.db import connect_db; conn = connect_db('retail.db'); cur = conn.cursor(); print(cur.execute('SELECT COUNT(*) FROM vw_store_sales').fetchone()[0], cur.execute('SELECT COUNT(*) FROM vw_customer_sales').fetchone()[0])"` → returns 1,003,420 store sales and 776,582 customer sales (boundary split 226,838 rows) → AC-6
- [ ] `uv run pytest tests/test_data_ingestion.py` → all 8 synthetic tests pass covering error handling, normalization, tie breaking, wholesale tokens, and exports → AC-10
- [ ] `uv run sqlfluff lint sql/ --dialect sqlite` → passes clean with 0 errors → AC-7
- [ ] `uv run ty check` → passes clean with 0 errors → AC-9
- [ ] `uv run ruff check .` → passes clean with 0 errors → AC-9

## Acceptance-criteria coverage

- AC-1: covered by commands 1, 3
- AC-2: covered by command 2
- AC-3: covered by commands 1, 6
- AC-4: covered by commands 1, 4
- AC-5: covered by commands 1, 4
- AC-6: covered by command 5
- AC-7: covered by commands 4, 7
- AC-8: covered by command 1
- AC-9: covered by commands 1, 8, 9
- AC-10: covered by command 6
