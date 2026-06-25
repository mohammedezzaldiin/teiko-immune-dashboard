"""
db.py — shared database layer.

Holds the schema definition, a connection helper, and the column-normalization
logic used by load_data.py and the dashboard. Keeping this in one place means
the loader and the app can never disagree about the schema or column names.
"""
from __future__ import annotations

import os
import sqlite3

# Path to the SQLite file (repo root). Override with env var for tests if needed.
DB_PATH = os.environ.get("TEIKO_DB", os.path.join(os.path.dirname(__file__), "teiko.db"))
CSV_PATH = os.environ.get("TEIKO_CSV", os.path.join(os.path.dirname(__file__), "cell-count.csv"))

# The five immune cell populations. The loader also auto-detects any *extra*
# numeric population columns, so adding a 6th population needs no code change —
# but these are the canonical ones the assignment specifies.
POPULATIONS = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]

# Everything that is NOT a population column is treated as metadata.
METADATA_COLS = {
    "project", "subject", "condition", "age", "sex",
    "treatment", "response", "sample", "sample_type",
    "time_from_treatment_start",
}

# Map common header variants -> our canonical metadata names. This makes the
# loader robust to the small wording differences seen in the wild (the spec
# prose says "indication"/"gender"/"sample_id" while the CSV uses
# "condition"/"sex"/"sample").
COLUMN_ALIASES = {
    "indication": "condition",
    "disease": "condition",
    "gender": "sex",
    "sample_id": "sample",
    "subject_id": "subject",
    "project_id": "project",
    "time_from_treatment": "time_from_treatment_start",
    "timepoint": "time_from_treatment_start",
}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE projects (
    project_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL UNIQUE
);

-- A subject's clinical attributes are constant across their samples, so they
-- live here (1 row per subject) rather than being repeated on every sample row.
CREATE TABLE subjects (
    subject_id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(project_id),
    condition  TEXT,
    age        INTEGER,
    sex        TEXT,
    treatment  TEXT,
    response   TEXT          -- 'yes' / 'no' / NULL (e.g. healthy controls)
);

-- One row per biological sample. A subject can have many samples (timepoints).
CREATE TABLE samples (
    sample_id                 TEXT PRIMARY KEY,
    subject_id                TEXT NOT NULL REFERENCES subjects(subject_id),
    sample_type               TEXT,            -- e.g. PBMC, tumor
    time_from_treatment_start INTEGER
);

-- Long ("tidy") format: one row per sample x population. This is the key design
-- choice — see README. It makes per-sample frequency a simple GROUP BY and lets
-- new populations arrive as rows, not schema changes.
CREATE TABLE cell_counts (
    sample_id  TEXT NOT NULL REFERENCES samples(sample_id),
    population TEXT NOT NULL,
    count      INTEGER NOT NULL,
    PRIMARY KEY (sample_id, population)
);

-- Indexes for the filter/aggregate patterns the analytics use.
CREATE INDEX idx_subjects_filters ON subjects(condition, treatment, response, sex);
CREATE INDEX idx_samples_subject  ON samples(subject_id);
CREATE INDEX idx_samples_filters  ON samples(sample_type, time_from_treatment_start);
CREATE INDEX idx_counts_population ON cell_counts(population);
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled and row access by name."""
    conn = sqlite3.connect(db_path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def normalize_columns(columns):
    """Lowercase/strip headers and apply aliases. Returns a {original: canonical} map."""
    mapping = {}
    for col in columns:
        key = str(col).strip().lower()
        mapping[col] = COLUMN_ALIASES.get(key, key)
    return mapping
