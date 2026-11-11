# 10-Step Project Roadmap: Customer Segmentation & Campaign Recommendations

Based on [Portfolio Project Brief Customer Segmentation and Campaign Recommendations.md](./Portfolio%20Project%20Brief%20Customer%20Segmentation%20and%20Campaign%20Recommendations.md) and the local dataset already in [`dataset/online_retail_II.xlsx`](./dataset/online_retail_II.xlsx), here is the step-by-step execution plan to take this project from raw spreadsheet to a recruiter-ready GitHub portfolio case study.

> **Local Environment Check:** `dataset/online_retail_II.xlsx` is already downloaded and contains two sheets (`Year 2009-2010` and `Year 2010-2011`) with columns `Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`, `Price`, `Customer ID`, and `Country`. Python (`3.13.5`), `sqlite3` (`3.49.1`), `pandas`, `openpyxl`, and `scikit-learn` are already installed, so you can use SQLite locally right away (or Postgres/MySQL if preferred).

---

## Step 1: Set Up the Repo Structure and AI Usage Log
- [ ] Initialize a Git repository (`git init`) and add a `.gitignore` (exclude large raw data files if over GitHub's limits, local `.db` files, and temporary exports).
- [ ] Create a clean folder structure:
  - `dataset/` (keep `online_retail_II.xlsx` untouched as raw input)
  - `scripts/` (data loader script)
  - `sql/` (`01_data_cleaning.sql`, `02_kpi_and_cohorts.sql`, `03_rfm_segmentation.sql`, `04_product_country_deep_dive.sql`)
  - `notebooks/` (optional K-means validation notebook)
  - `powerbi/` (`.pbix` file + exported screenshots in `images/`)
  - `docs/` (`ai_log.md` and the 1-page recommendations memo)
- [ ] Start `docs/ai_log.md` now so you record prompts, AI-drafted SQL/insights, and how you verified them as you go.

**Deliverable progress:** Repo skeleton and AI workflow tracking ready.

---

## Step 2: Profile and Load the Raw Excel Data into SQL
- [ ] Write a short Python loader script (`scripts/load_to_sql.py`) using `openpyxl` / `pandas` + `sqlite3` (or your SQL engine of choice) to combine both sheets (`Year 2009-2010` and `Year 2010-2011`) into a single staging table `raw_transactions`.
- [ ] Cast mixed-type columns safely before inserting:
  - Store `Invoice` and `StockCode` as `TEXT` (because cancellations start with `'C'` and codes like `'85123A'` are alphanumeric).
  - Keep `Customer ID` nullable and standardize column names to `snake_case` (`invoice`, `stock_code`, `description`, `quantity`, `invoice_date`, `price`, `customer_id`, `country`).
- [ ] Run initial profiling queries: verify total row count (~1,067,371 rows), date range (`2009-12-01` to `2011-12-09`), null counts, negative quantities/prices, and duplicate lines across the two sheets.

**Deliverable progress:** Queryable `raw_transactions` SQL table + baseline row-count audit.

---

## Step 3: Clean and Audit the Data in SQL
- [ ] Write `sql/01_data_cleaning.sql` to create `clean_transactions` and produce a **row-removal audit table** documenting how many rows each rule removes:
  1. **Missing `customer_id`** (~243,000 rows / ~23% — note this caveat for customer-level vs. total store revenue).
  2. **Cancellations** (`invoice LIKE 'C%'`).
  3. **Zero or negative `quantity` and `price`**.
  4. **Non-product lines** (inspect distinct non-standard `stock_code` values such as `POST`, `D`, `M`, `DOT`, `BANK CHARGES`, `CRUK`, `ADJUST`, etc., and exclude non-merchandise fees/adjustments).
  5. **Exact duplicate rows** (check if any duplicate lines exist across sheet boundaries and document your deduplication rule).
- [ ] Add derived columns (`line_revenue = quantity * price`, `order_date`, `order_month`).

**Deliverable progress:** `sql/01_data_cleaning.sql` + verified `clean_transactions` table and cleaning audit log.

---

## Step 4: Build Core Commercial KPIs and Cohort Retention in SQL
Answer **Business Questions #1 and #2** in `sql/02_kpi_and_cohorts.sql`:
- [ ] **Monthly KPI trend:** Calculate monthly revenue, order count (`COUNT(DISTINCT invoice)`), active customers (`COUNT(DISTINCT customer_id)`), Average Order Value (`revenue / orders`), and revenue per active customer.
- [ ] **Repeat purchase rate:** Calculate the share of customers with `COUNT(DISTINCT invoice) > 1` vs. one-time buyers (overall and by year/cohort).
- [ ] **Monthly cohort retention:** Assign each customer their `cohort_month = MIN(order_month)`, compute `cohort_index` (months elapsed since first order: `0, 1, 2, ...`), and compute active customer counts and retention % per cohort.

**Deliverable progress:** `sql/02_kpi_and_cohorts.sql` + traceable tables/views for KPIs and cohort retention.

---

## Step 5: Build RFM Scores and Customer Segments in SQL
Answer **Business Questions #3 and #4** in `sql/03_rfm_segmentation.sql`:
- [ ] Set a fixed analysis reference date (`2011-12-10`, one day after the max transaction date) so Recency is consistent.
- [ ] Aggregate per customer:
  - **Recency (`R`):** Days since last invoice.
  - **Frequency (`F`):** Distinct invoice count.
  - **Monetary (`M`):** Total `line_revenue`.
- [ ] Score R, F, and M from `1` to `5` using `NTILE(5)` (order `Recency DESC` so most recent = `5`; order `Frequency ASC` and `Monetary ASC` so highest = `5`).
- [ ] Map RFM score rules into clear business segments (`Champions`, `Loyal`, `Potential Loyalists`, `New`, `At Risk`, `Hibernating`, etc.).
- [ ] Build the **segment summary table**: customer count, % of customers, total revenue, % of revenue (the **80/20 view**), average R/F/M, and total revenue sitting in `At Risk` / `Hibernating` segments.

**Deliverable progress:** `sql/03_rfm_segmentation.sql` + customer-level and segment-level summary views.

---

## Step 6: Run Product & Country Deep-Dive (+ Optional K-Means Validation)
Answer **Business Question #5** and validate your segments:
- [ ] Write `sql/04_product_country_deep_dive.sql` to find which `stock_code` / `description` products and `country` markets **over-index** in `Champions` and `Loyal` segments compared to the store-wide baseline (e.g., segment revenue share vs. overall revenue share / index ratio).
- [ ] Inspect order quantities and revenue distribution to quantify the **wholesale buyer caveat** (e.g., top B2B accounts vs. standard retail buyers).
- [ ] *(Optional validation)* Create `notebooks/rfm_kmeans_validation.ipynb` using `pandas` + `scikit-learn`: log-transform skewed R, F, M values, standardize with `StandardScaler`, run K-means clustering, and verify that unsupervised clusters align well with your SQL RFM segments.

**Deliverable progress:** `sql/04_product_country_deep_dive.sql` + optional validation notebook.

---

## Step 7: Build the Two-Page Power BI Dashboard
Export your clean SQL views (or connect Power BI directly to your SQL database) and build a two-page report in `powerbi/`:
- [ ] **Page 1 — Executive KPI Overview:**
  - KPI cards (Total Revenue, Orders, Active Customers, AOV, Repeat Purchase Rate)
  - Monthly Revenue & Orders trend chart
  - Monthly Cohort Retention heatmap/matrix
  - Segment Revenue vs. Customer Share (80/20 Pareto view)
- [ ] **Page 2 — Segment Explorer:**
  - Interactive filters/slicers (Segment, Country, Year/Month)
  - Segment KPI breakdown & revenue-at-risk callout
  - RFM profile / Recency vs. Monetary view
  - Top over-indexing products and countries by selected segment
- [ ] **Audit every number:** Verify that every card and table total in Power BI reconciles 1-to-1 with your SQL query outputs. Save clean, high-resolution screenshots of both pages to `images/`.

**Deliverable progress:** Two-page `.pbix` dashboard + verified screenshots.

---

## Step 8: Draft Segment Campaign Recommendations & A/B Test Hypotheses
Create a **1-page recommendations memo** (`docs/campaign_recommendations_memo.md`, optionally exported to PDF) addressed to the Marketing and E-commerce teams:
- [ ] Put **headline findings first** (e.g., top segments driving ~X% of revenue, cohort retention drop-off after month 1, and revenue sitting in `At Risk`).
- [ ] Build a structured action plan for each segment (`Champions`, `Loyal`, `Potential Loyalists`, `New`, `At Risk`, `Hibernating`) with:
  - **Commercial action / channel** (e.g., VIP loyalty perks, cross-sell bundles, second-order nudge, day-60 win-back email)
  - **Hypothesis** (why this segment should respond)
  - **A/B test design** (treatment vs. holdout group, primary metric such as 30-day repurchase rate or AOV, and guardrail metrics)
- [ ] Explicitly state that these are **test-ready hypotheses rather than proven uplift**, because the dataset contains no historical promotion or campaign tracking.

**Deliverable progress:** 1-page Marketing & E-commerce recommendations memo.

---

## Step 9: Document AI-Assisted Analytics & Dataset Caveats
Finalize your supporting documentation in `docs/ai_log.md` (and summarize it for the README):
- [ ] Include 3–5 concrete examples of how you used an LLM or Power BI Q&A (e.g., drafting SQL window/cohort templates, exploring anomalies, drafting memo summaries).
- [ ] For each example, document **how you verified or corrected the output** (e.g., fixing `NTILE` sort direction on Recency, reconciling Power BI DAX measures against SQL totals, checking excluded `StockCode`s).
- [ ] Clearly list the three core data caveats:
  1. ~23% of rows lack `Customer ID` and are excluded from customer-level RFM.
  2. Many accounts behave as wholesalers (high volume / B2B ordering).
  3. No promotion, channel, or margin data exists in the dataset.

**Deliverable progress:** Auditable AI workflow log and caveat notes.

---

## Step 10: Write the Case-Study README, Run the "Done" Audit, and Publish
- [ ] Write `README.md` at the repo root structured as an executive case study:
  1. **Business Problem & Context** (2–3 sentences)
  2. **Approach & Data Cleaning Summary** (with row-removal table and links to `sql/`)
  3. **3–4 Key Findings** (with Power BI dashboard screenshots embedded)
  4. **Segment Recommendations Summary** (table + link to the 1-page memo)
  5. **AI-Assisted Workflow & Limitations**
  6. **How to Reproduce** (exact steps to run loader + SQL scripts)
- [ ] Run the final **"Done" audit**:
  - **60-second test:** Can a recruiter grasp your top findings and business impact in 60 seconds just by reading `README.md`?
  - **Traceability test:** Can an interviewer open `sql/` and reproduce every single number shown on the Power BI dashboard?
- [ ] Commit all work cleanly and push to GitHub.

---

## Optional Phase 2 (Only After Core Project Ships)
Once Steps 1–10 are published on GitHub, optionally add a separate `phase2_ga4/` folder or repo using BigQuery's `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` dataset to build an e-commerce purchase funnel (`view_item` → `add_to_cart` → `begin_checkout` → `purchase`) and traffic source comparison.

