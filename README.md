# Loblaw Bio — Immune Cell Population Analysis

**🔗 Live dashboard:** https://teiko-immune-dashboard-hy3ttuvewtr69eisx8esqe.streamlit.app/ · **Repo:** https://github.com/mohammedezzaldiin/teiko-immune-dashboard

A small, reproducible pipeline + dashboard for analyzing immune cell population
counts from a clinical trial of **miraclib**. It loads `cell-count.csv` into a
normalized SQLite database, computes per-sample population frequencies, compares
responders vs non-responders, and breaks down a baseline subset — all surfaced
in an interactive Streamlit dashboard.

> **Data file.** This repo ships with the real `cell-count.csv` (10,500 samples
> across 3 projects). The loader is tolerant of common header variants
> (`sex`/`gender`, `condition`/`indication`, `sample`/`sample_id`, etc.), and
> `make_synthetic_csv.py` can regenerate a small stand-in file for local testing
> if needed. To use a different dataset, drop it in as `cell-count.csv` and re-run
> `make pipeline` — every table, plot, and number regenerates from it.

---

## Quickstart (GitHub Codespaces)

```bash
make setup       # install dependencies (requirements.txt)
make pipeline    # build DB + load data (Part 1), then run analysis (Parts 2–4)
make dashboard   # launch the interactive dashboard
make test        # (optional) run the test suite
```

`make pipeline` writes the database to `teiko.db` and all result tables/plots to
`outputs/`. `make dashboard` starts Streamlit; in Codespaces, open the forwarded
port (8501) when prompted.

**Run directly without make:**
```bash
python load_data.py        # Part 1
python analysis.py         # Parts 2–4
streamlit run dashboard.py # dashboard
```

---

## Repository structure

```
.
├── load_data.py          # Part 1: schema init + CSV ingest -> teiko.db
├── analysis.py           # Parts 2–4: frequency table, stats, plots, subset queries
├── dashboard.py          # Streamlit dashboard (reuses analysis.py functions)
├── db.py                 # shared: schema DDL, connection helper, column aliases
├── make_synthetic_csv.py # dev-only generator for a stand-in cell-count.csv
├── test_pipeline.py      # pytest sanity/integration tests
├── cell-count.csv        # input data (replace with the real file)
├── requirements.txt
├── Makefile              # setup / pipeline / dashboard / test
├── outputs/              # generated tables (.csv) + boxplot (.png)
└── README.md
```

### Why it's structured this way
- **`db.py` is the single source of truth** for the schema and column handling, so
  `load_data.py` and `dashboard.py` can never drift apart.
- **`analysis.py` exposes pure functions** (`frequency_table`, `responder_stats`,
  `baseline_subset`, …) that both the CLI `main()` and the dashboard call. The
  analysis logic is written once and tested once; the dashboard is just a view.
- **The loader is idempotent** — it rebuilds `teiko.db` from scratch each run, so
  the database always matches the current CSV and there's no migration state to
  manage during grading.

---

## Database schema

Four tables in third-normal form:

```
projects (project_id PK, project_name)
    │ 1
    │
    │ ∞
subjects (subject_id PK, project_id FK→projects,
          condition, age, sex, treatment, response)
    │ 1
    │
    │ ∞
samples  (sample_id PK, subject_id FK→subjects,
          sample_type, time_from_treatment_start)
    │ 1
    │
    │ ∞
cell_counts (sample_id FK→samples, population, count,  PK(sample_id, population))
```

### Design rationale
- **Subject vs sample separation.** Clinical attributes (`condition`, `age`,
  `sex`, `treatment`, `response`) are properties of a *patient*, constant across
  their samples, so they live on `subjects` — not repeated on every row. A patient
  contributes many `samples` (different timepoints), and each sample has its own
  `sample_type` and `time_from_treatment_start`.
- **Long ("tidy") cell counts.** Instead of five wide columns
  (`b_cell, cd8_t_cell, …`), counts are stored one row per *(sample, population)*.
  This is the most consequential choice:
  - Per-sample frequency becomes a single `GROUP BY`/window query (Part 2) with no
    hard-coded column names.
  - Adding a 6th population is a data change, not a schema migration — the loader
    auto-detects any non-metadata numeric column as a population.
  - Filtering/aggregating by population (Part 3) is a simple `WHERE population = …`.
- **Indexes** are added for the actual access patterns used by the analytics:
  filtering subjects by `condition/treatment/response/sex`, joining samples to
  subjects, filtering samples by `sample_type`/timepoint, and grouping counts by
  `population`.

### How this scales to hundreds of projects / thousands of samples
- The normalized model means metadata is stored once per subject regardless of how
  many samples or populations exist; storage grows roughly linearly with
  *samples × populations*, not redundantly.
- The long `cell_counts` table is the only one that grows large, and it's exactly
  the shape analytic engines like best. The indexed filter columns keep the
  responder/baseline queries fast as volume grows.
- For very large scale, the same schema ports directly to Postgres (swap the
  connection in `db.py`); the long table is naturally partitionable by `project`
  or `population`, and common cuts (per-sample totals, per-cohort frequencies) can
  be materialized as views or summary tables without touching the loader.
- New analytics generally become new SQL against the same tidy tables rather than
  new ETL — e.g. longitudinal trajectories use `time_from_treatment_start`,
  cross-population ratios are self-joins on `cell_counts`.

---

## What each part produces

**Part 2 — frequency table** (`outputs/part2_frequency_table.csv`)
Columns `sample, total_count, population, count, percentage`, where `percentage`
is each population's share of that sample's total cell count.

**Part 3 — responders vs non-responders** (melanoma · miraclib · PBMC)
- `outputs/part3_boxplots.png` — boxplot per population, responders vs
  non-responders, with individual points overlaid.
- `outputs/part3_stats.csv` — per-population **Mann–Whitney U** test (two-sided;
  non-parametric, appropriate for small clinical n and non-normal frequencies)
  with group medians, raw p-values, and **Benjamini–Hochberg FDR** q-values across
  the five populations. A population is called significant at **q < 0.05**.

**Part 4 — baseline subset** (melanoma · miraclib · PBMC · `time = 0`)
- `outputs/part4_baseline_samples.csv` — the matching samples.
- `part4_samples_per_project.csv`, `part4_subjects_by_response.csv`,
  `part4_subjects_by_sex.csv` — the requested breakdowns.
- Average B-cell **count** for melanoma **males**, **responders**, at `t=0`,
  reported to two decimals (printed by `analysis.py` and shown on the dashboard).

---

## Dashboard

Streamlit app with four tabs: **Overview** (dataset composition), **Part 2**
(filterable frequency table + composition chart), **Part 3** (interactive boxplots
+ stats table + significance call-out), **Part 4** (baseline subset + breakdowns +
the B-cell metric). It auto-builds `teiko.db` on first load if it's missing.

**Live dashboard:** https://teiko-immune-dashboard-hy3ttuvewtr69eisx8esqe.streamlit.app/

---

## Testing

`make test` (or `pytest -q`) runs two suites:

- **`test_pipeline.py`** — data-agnostic invariants that hold for *any* valid
  input: all tables populated, Part 2 percentages sum to 100% per sample, the
  Part 3 cohort is correctly filtered, p/q-values are valid probabilities, and the
  Part 4 subset matches all baseline criteria.
- **`test_real_data.py`** — ground-truth regression tests that lock in the exact
  verified answers for the shipped 10,500-sample dataset (table counts, Part 3
  cohort sizes, the Part 4 breakdowns, and the headline average B-cell count of
  `10401.28`). These self-skip if a different dataset is in place, so they never
  produce false failures.

All 12 tests pass on the shipped data.