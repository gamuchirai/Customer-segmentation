# Scope: Customer Segmentation and Campaign Recommendations

Two year retail transaction analysis that sizes customer value, finds churn risk, and delivers testable marketing recommendations for digital commerce and marketing teams.

**Build approach:** Tracer Bullet (vertical slices built end to end through data, queries, and reporting before thickening the next slice).
**Workflow:** Beta (after `/develop`, run `/check verify`, then `/test`). The project default level of rigor. `/architect` is the recommended first stop for a feature with a real decision, but skippable when you already know the build. Any feature can carry its own tag (e.g. `· GA`) to do more or less.

_These are recommendations to keep your build orderly, not requirements. Skip anything that does not fit: if you already know how to build a feature, use `/develop` and skip `/architect`. You decide when a feature is `done`._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack and architecture | Foundation | in-progress |
| 2 | Coding standards and tooling | Foundation | in-progress |
| 3 | Data model and dual view contract | Foundation | planned |
| 4 | Data ingestion and cleaning pipeline | Slice 1 | planned |
| 5 | Executive KPIs and BI overview connection | Slice 1 | planned |
| 6 | Monthly cohort retention analysis | Slice 2 | planned |
| 7 | RFM scoring and customer segments | Slice 3 | planned |
| 8 | Clustering validation | Slice 3 | planned |
| 9 | Product and country deep dive plus wholesale audit | Slice 4 | planned |
| 10 | Campaign recommendations memo | Slice 5 | planned |
| 11 | AI workflow log and case study README | Slice 5 | planned |

## Foundations

### 1. Stack and architecture · in-progress
Decide the data, analytics, and reporting stack and scaffold the clean directory skeleton, repository ignore rules, and tracking baseline.
**Done when:** the stack is recorded in a spec, raw datasets and local database binaries are excluded from version control, and the folder layout boots cleanly.
spec [0001](../specs/0001-stack-and-architecture.md) · code in .gitignore, scripts/, tests/, docs/ai_log.md
- [x] Decide the stack (spec): `/architect stack and architecture`
- [x] Scaffold from the decision: `/develop stack and architecture`
- [ ] Verify it: `/check verify stack and architecture`
- [ ] Test it: `/test stack and architecture`

### 2. Coding standards and tooling · in-progress
Capture conventions, then install linting, formatting, commit checks, and continuous integration from the scaffolded project.
**Done when:** root `AGENTS.md` reflects the project conventions, and linting, formatting, commit checks, and tests run cleanly.
spec [0001](../specs/0001-stack-and-architecture.md) · code in pyproject.toml, uv.lock, .sqlfluff, .pre-commit-config.yaml, .github/workflows/ci.yml
- [x] Capture conventions + tooling choices: `/audit`
- [x] Install the tooling: `/develop tooling`
- [ ] Check it runs clean: `/test`

### 3. Data model and dual view contract · needs a decision
Define staging and cleaned transaction entities, row removal audit logging, dual denominator boundaries (store wide valid sales vs identified customers), and wholesale account flags.
**Done when:** schemas, derived fields, and metric boundaries support KPIs, cohorts, RFM, and deep dives without breaking changes later.
- [ ] Design it (spec): `/architect data model`

## Slice 1: Core pipeline and Executive KPI thread

### 4. Data ingestion and cleaning pipeline · needs a decision
Load raw workbook sheets safely into staging, apply explicit cleaning rules (cancellations, missing customer IDs, zero or negative values, postage and fee lines, exact duplicates), and log every removed row count.
**Done when:** raw and cleaned tables populate repeatably, raw workbook stays untouched, and every cleaning rule reports exact removed row counts in the audit table.
- [ ] Design it (spec): `/architect data ingestion and cleaning`

### 5. Executive KPIs and BI overview connection · needs a decision
Compute monthly revenue, distinct order counts, active customers, average order value, revenue per active customer, and repeat purchase rate, and wire the initial BI model and Executive Overview page.
**Done when:** KPI trend metrics and Executive Overview cards render from live queries and reconcile one to one with query totals.
- [ ] Design it (spec): `/architect executive KPIs and BI overview`

## Slice 2: Cohort retention thread

### 6. Monthly cohort retention analysis
Assign each identified customer an acquisition cohort month, compute elapsed cohort index values and retention percentages, and add the cohort retention matrix to the Executive Overview page.
**Done when:** cohort retention curves and matrix totals reconcile one to one with identified customer queries and display decay patterns clearly.
- [ ] Build it: `/develop monthly cohort retention analysis`

## Slice 3: RFM segmentation and clustering validation

### 7. RFM scoring and customer segments · needs a decision
Set a fixed reference date, score recency, frequency, and monetary value in quintiles, map scores into business segments (`Champions`, `Loyal`, `Potential Loyalists`, `New`, `At Risk`, `Hibernating`), compute the 80/20 summary, and build the Segment Explorer BI page.
**Done when:** every identified customer belongs to one segment, revenue at risk and Pareto shares reconcile one to one, and Segment Explorer filters interactively by segment, country, and month.
- [ ] Design it (spec): `/architect RFM scoring and customer segments`

### 8. Clustering validation · needs a decision
Log transform and standardize customer RFM metrics, run unsupervised clustering, and measure how closely natural clusters align with the rule based segments.
**Done when:** cluster diagnostics explain the chosen cluster count and quantify agreement plus wholesale outlier separation against the SQL segments.
- [ ] Design it (spec): `/architect clustering validation`

## Slice 4: Product, country, and wholesale deep dive

### 9. Product and country deep dive plus wholesale audit
Identify products and country markets over indexing in top segments, quantify wholesale account concentration, wire top items and markets into Segment Explorer, and run full dashboard verification with exported page screenshots.
**Done when:** over indexing ratios, wholesale caveats, and every visual across both BI pages reconcile one to one with query outputs and clean screenshots are saved.
- [ ] Build it: `/develop product and country deep dive`

## Slice 5: Stakeholder deliverables and case study ship

### 10. Campaign recommendations memo · needs a decision
Write a one page Marketing and Digital Commerce memo leading with headline findings, per segment commercial actions, testable hypotheses, A/B test holdout metrics, and explicit no campaign history caveats, plus export a polished document version.
**Done when:** the one page markdown memo and exported document use verified numbers only and clearly separate test hypotheses from proven uplift.
- [ ] Design it (spec): `/architect campaign recommendations memo`

### 11. AI workflow log and case study README
Document concrete AI prompt and verification examples alongside the three dataset caveats, and publish an executive case study `README.md` with embedded screenshots and exact local reproduction steps.
**Done when:** a reviewer grasps top findings in 60 seconds from `README.md`, can reproduce every number from queries locally, and all three caveats are clearly stated.
- [ ] Build it: `/develop AI workflow log and case study README`

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Web purchase funnel add on**: optional second phase purchase funnel (`view_item` through `purchase`) and traffic source comparison using public analytics event logs · needs a decision

## Legend

**The decision box.** Every feature carries exactly one, the sub task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack and architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | **`/architect` at spec capture** | `Design it` ticked; spec linked; `Build it: /develop <feature>` + **2 to 5 milestones**; the tier's closing boxes (`Verify it` Alpha+, `Test it` Beta+, `Review it` + `Document it` GA); any surfaced follow up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` + milestones ticked; `Verify it` ticked |
| `done` | **you, when you decide it is** (any skill sets it when you say so); `/sync` reconciles | boxes you ran ticked, skipped ones marked skipped; the tier's last stage (`Prototype` → after `/develop`; `Alpha` → after `/check verify`; `Beta`/`GA` → after `/test`) is the suggested point to call it done; `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for standards and tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` → `in-progress` → `done`, plus `existing` (before workflow) and `dropped` (removed from scope, kept for history).
- **Approach tag** beside a heading (e.g. `· Facade`) overrides the project default for that feature; no tag = inherits it.
- **Workflow tier tag** beside a heading (e.g. `· GA`, `· Prototype`) sets that one feature's rigor above or below the project default; no tag inherits the default. It decides the feature's check boxes and each skill's next suggestion.
- **Workflow** (header line) is the project default, what runs after `/develop`: **Prototype** = nothing (trust develop's own build time self check); **Alpha** = `/check verify`; **Beta** = `/check verify` then `/test`; **GA** = adds a fresh model `/check review` then `/document`. A feature built on an unratified decision (an `Assumed` spec) stays flagged, but that never blocks `done`.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
