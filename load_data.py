#!/usr/bin/env python3
"""
load_data.py — Part 1: Data Management.

Run with:  python load_data.py

Creates teiko.db in the repo root, builds the relational schema, and loads every
row of cell-count.csv into it. Re-running is safe: it rebuilds from scratch
(idempotent), so the database always matches the current CSV.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

import db


def load(csv_path: str = db.CSV_PATH, db_path: str = db.DB_PATH) -> None:
    if not os.path.exists(csv_path):
        sys.exit(
            f"ERROR: '{csv_path}' not found.\n"
            "Place the real cell-count.csv in the repo root (or run "
            "`python make_synthetic_csv.py` to generate a test file)."
        )

    # --- read + normalize -------------------------------------------------
    raw = pd.read_csv(csv_path)
    colmap = db.normalize_columns(raw.columns)
    df = raw.rename(columns=colmap)

    # Identify population columns = anything that isn't known metadata.
    pop_cols = [c for c in df.columns if c not in db.METADATA_COLS]
    if not pop_cols:
        sys.exit("ERROR: no population (count) columns detected in the CSV.")

    required_meta = {"project", "subject", "sample"}
    missing = required_meta - set(df.columns)
    if missing:
        sys.exit(f"ERROR: CSV is missing required column(s): {sorted(missing)}")

    # Coerce types; blank/NaN response/age -> NULL.
    if "response" in df.columns:
        df["response"] = df["response"].apply(
            lambda v: None if (pd.isna(v) or str(v).strip() == "") else str(v)
        )
    for numeric in ["age", "time_from_treatment_start", *pop_cols]:
        if numeric in df.columns:
            df[numeric] = pd.to_numeric(df[numeric], errors="coerce")

    def clean(v):
        """NaN/empty -> None for safe SQLite insertion."""
        return None if (v is None or (not isinstance(v, str) and pd.isna(v))) else v

    # --- (re)build schema -------------------------------------------------
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = db.get_connection(db_path)
    conn.executescript(db.SCHEMA)

    # --- projects ---------------------------------------------------------
    projects = sorted(df["project"].dropna().unique())
    conn.executemany("INSERT INTO projects (project_name) VALUES (?)", [(p,) for p in projects])
    project_ids = {
        row["project_name"]: row["project_id"]
        for row in conn.execute("SELECT project_id, project_name FROM projects")
    }

    # --- subjects (one row per subject; take first occurrence) ------------
    def col(name):
        return name if name in df.columns else None

    subj_rows = []
    seen = set()
    for _, r in df.iterrows():
        s = r["subject"]
        if s in seen:
            continue
        seen.add(s)
        subj_rows.append((
            s,
            project_ids[r["project"]],
            clean(r.get("condition")),
            None if pd.isna(r.get("age")) else int(r["age"]),
            clean(r.get("sex")),
            clean(r.get("treatment")),
            clean(r.get("response")),
        ))
    conn.executemany(
        "INSERT INTO subjects (subject_id, project_id, condition, age, sex, treatment, response) "
        "VALUES (?,?,?,?,?,?,?)",
        subj_rows,
    )

    # --- samples ----------------------------------------------------------
    sample_rows = []
    seen_samples = set()
    for _, r in df.iterrows():
        sid = r["sample"]
        if sid in seen_samples:
            continue
        seen_samples.add(sid)
        tp = r.get("time_from_treatment_start")
        sample_rows.append((
            sid,
            r["subject"],
            clean(r.get("sample_type")),
            None if pd.isna(tp) else int(tp),
        ))
    conn.executemany(
        "INSERT INTO samples (sample_id, subject_id, sample_type, time_from_treatment_start) "
        "VALUES (?,?,?,?)",
        sample_rows,
    )

    # --- cell_counts (wide -> long) --------------------------------------
    long_df = df.melt(
        id_vars=["sample"], value_vars=pop_cols,
        var_name="population", value_name="count",
    ).dropna(subset=["count"])
    count_rows = [
        (r["sample"], r["population"], int(r["count"]))
        for _, r in long_df.iterrows()
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO cell_counts (sample_id, population, count) VALUES (?,?,?)",
        count_rows,
    )

    conn.commit()

    # --- summary ----------------------------------------------------------
    def n(table):
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    print("Loaded cell-count.csv into", db_path)
    print(f"  projects   : {n('projects')}")
    print(f"  subjects   : {n('subjects')}")
    print(f"  samples    : {n('samples')}")
    print(f"  cell_counts: {n('cell_counts')}  (populations: {', '.join(pop_cols)})")
    conn.close()


if __name__ == "__main__":
    load()
