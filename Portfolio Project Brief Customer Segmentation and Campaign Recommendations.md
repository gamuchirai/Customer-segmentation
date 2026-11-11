# Portfolio Project Brief: Customer Segmentation and Campaign Recommendations

Prepared November 11, 2026 as a portfolio project for Business Analyst roles in digital commerce and customer segmentation

## Why this project

A customer segmentation and campaign recommendation project hits the core responsibilities of a digital commerce Business Analyst role head-on: defining customer segments and optimising sales actions. It also covers KPI tracking, SQL, BI, and turning analysis into recommendations for Marketing and E-commerce teams. It is small enough to finish in one or two weekends.

## Dataset

Use **Online Retail II** from the UCI Machine Learning Repository: https://archive.ics.uci.edu/dataset/502/online+retail+ii (also mirrored on Kaggle). It is free under a CC BY 4.0 license.

- It holds every transaction of a UK-based, online-only gift-ware retailer between 1 December 2009 and 9 December 2011, a total of 1,067,371 rows.
- Fields: invoice, product code, description, quantity, date, unit price, customer ID and country.
- Cancellations are flagged by an invoice code that starts with the letter C.
- Caveats to address in your write-up: about 243,000 rows (roughly 23%) have no customer ID, and many of the customers are wholesalers. The data has no promotion information, so frame the project as a generic digital commerce case.

## Project brief

**Title:** From RFM to Revenue: Customer Segmentation and Campaign Recommendations for an Online Retailer

**Scenario:** You are the Business Analyst for an online retailer's e-commerce team. Marketing sends the same newsletter to everyone, and nobody knows which customers drive revenue, which are drifting away, or where a campaign would pay off.

**Problem statement:** Identify distinct customer segments from two years of transactions, size each segment's value, and recommend a specific commercial action for each one.

## Business questions to answer

1. What do revenue, orders, average order value and active customers look like month to month?
2. What share of customers is repeat, and how does retention decay by acquisition cohort?
3. Which customer segments exist, and how much revenue does each produce (the 80/20 view)?
4. Which segments are at risk of churning, and what are they worth?
5. Which products and countries over-index in the best segments?

## Method

1. **Clean in SQL.** Load the data into MySQL, Postgres or SQLite. Remove cancellations, rows without a customer ID, zero or negative prices and quantities, and non-product lines such as postage. Document every rule and how many rows it removed.
2. **Build KPIs in SQL.** Revenue, orders, AOV, revenue per customer, repeat purchase rate and monthly cohort retention.
3. **Segment with RFM.** Score recency, frequency and monetary value in SQL using NTILE, and label segments such as Champions, Loyal, Potential Loyalists, New, At Risk and Hibernating. Optionally run K-means in Python to check that the rule-based segments hold up.
4. **Build the dashboard** in Power BI, in two pages: an executive KPI overview, then a segment explorer with filters.
5. **Write recommendations.** For each segment, give an action, a hypothesis and a test. For example: "At Risk, high-value customers get a win-back email at day 60 of inactivity. Run an A/B test against a holdout, with 30-day repurchase rate as the success metric." Because the data has no campaign history, present these as test-ready hypotheses, not proven uplift. Saying so openly looks more credible to recruiters.
6. **Use AI-assisted analytics and document it.** Use an LLM or Power BI's natural-language Q&A to draft SQL, speed up exploration and draft insight text. Add a short README section showing the prompts you used and how you verified the output. Roles like this ask for exactly this skill.

## Deliverables

1. A GitHub repo with the SQL scripts (cleaning, KPIs, RFM) and an optional Python notebook.
2. A two-page Power BI dashboard, with screenshots in the README.
3. A one-page recommendations memo addressed to the Marketing and E-commerce teams, with the headline findings first.
4. A README written as a case study: problem, approach, 3 or 4 key findings, recommendations, and limitations.

**Done means:** a recruiter can understand your top findings in 60 seconds from the README, and an interviewer can open the SQL and trace any number on the dashboard.

## Optional phase 2: GA4

Roles like this often name GA4, and Google publishes a free sample dataset: an obfuscated export of Google Merchandise Store ecommerce data from November 2020 to January 2021, queryable in BigQuery. You need a Google Cloud project with the BigQuery API enabled. The table path is `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`.

A simple add-on would be a purchase funnel (view item, add to cart, begin checkout, purchase) plus a traffic source comparison. Keep this separate from the core project so the first one ships.
