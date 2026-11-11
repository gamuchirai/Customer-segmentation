# AI Assisted Analytics and Verification Log

This log records how AI assistance was used across SQL drafting, Python transforms, validation, and stakeholder writing, together with the concrete checks used to verify or correct every output.

## Verification Standard

- Never accept generated SQL, Python logic, or summary figures without running queries and reconciling totals directly against SQLite outputs.
- Record the prompt or workflow step, what AI generated, and what verification confirmed or caught.

## Dataset Caveats Tracker

Keep these three dataset limits visible across every downstream query, chart, and recommendation:

1. **Missing customer IDs**: Roughly 23% of raw rows (~243,000 rows) lack `customer_id`; track store wide valid revenue separately from identified customer metrics.
2. **Wholesale accounts**: Many accounts behave as high volume B2B wholesale buyers rather than typical retail shoppers, which skews unsegmented monetary distributions.
3. **No campaign or margin history**: The dataset contains no promotion codes, channel attribution, or product cost data, so segment recommendations must be framed as testable hypotheses rather than proven uplift.

## Workflow Entries

| # | Date | Area | How AI Helped | How Output Was Verified or Corrected |
|---|---|---|---|---|
| 1 | 2026-11-11 | Stack and architecture | Evaluated local environment, Windows Power BI connectivity, and packaging options into Spec 0001 | Verified local `uv`, Python `3.13.5`, Power BI Desktop install, and missing Windows ODBC drivers; closed 5 setup gaps via independent cross check |

