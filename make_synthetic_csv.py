"""
make_synthetic_csv.py  (DEV ONLY)
---------------------------------
Generates a synthetic `cell-count.csv` with the SAME schema as the real Teiko
file so the pipeline can be developed and tested end-to-end.

>>> REPLACE the generated cell-count.csv with the real one before submitting. <<<
The numbers produced by the pipeline are only meaningful for the real data.

Columns:
  project, subject, condition, age, sex, treatment, response,
  sample, sample_type, time_from_treatment_start,
  b_cell, cd8_t_cell, cd4_t_cell, nk_cell, monocyte
"""
import csv
import random

random.seed(42)

PROJECTS = ["prj1", "prj2", "prj3"]
CONDITIONS = ["melanoma", "lung", "healthy"]
TREATMENTS = ["miraclib", "phauximab", "none"]
SAMPLE_TYPES = ["PBMC", "tumor"]
TIMEPOINTS = [0, 7, 14]
POPS = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]

rows = []
subject_counter = 0

# Build a population of subjects with samples across timepoints.
for _ in range(40):
    subject_counter += 1
    subject = f"sbj{subject_counter:03d}"
    project = random.choice(PROJECTS)
    condition = random.choices(CONDITIONS, weights=[0.5, 0.3, 0.2])[0]
    age = random.randint(30, 80)
    sex = random.choice(["M", "F"])
    # healthy subjects get no treatment/response
    if condition == "healthy":
        treatment = "none"
        response = ""  # NA
    else:
        treatment = random.choices(TREATMENTS[:2], weights=[0.6, 0.4])[0]
        response = random.choice(["yes", "no"])

    # responders tend to have a slightly different immune profile (signal to find)
    responder = response == "yes"

    n_samples = random.choice([1, 2, 3])
    chosen_timepoints = sorted(random.sample(TIMEPOINTS, n_samples))
    for tp in chosen_timepoints:
        sample_type = random.choices(SAMPLE_TYPES, weights=[0.7, 0.3])[0]
        sample = f"s{len(rows) + 1:04d}"

        # base counts
        b = random.randint(8000, 16000)
        cd8 = random.randint(15000, 30000)
        cd4 = random.randint(20000, 40000)
        nk = random.randint(5000, 12000)
        mono = random.randint(10000, 22000)

        # inject a mild, detectable responder signal in cd8 + b for miraclib melanoma PBMC
        if responder and treatment == "miraclib" and condition == "melanoma" and sample_type == "PBMC":
            cd8 = int(cd8 * random.uniform(1.25, 1.55))
            b = int(b * random.uniform(1.15, 1.35))
            mono = int(mono * random.uniform(0.7, 0.9))

        rows.append({
            "project": project,
            "subject": subject,
            "condition": condition,
            "age": age,
            "sex": sex,
            "treatment": treatment,
            "response": response,
            "sample": sample,
            "sample_type": sample_type,
            "time_from_treatment_start": tp,
            "b_cell": b,
            "cd8_t_cell": cd8,
            "cd4_t_cell": cd4,
            "nk_cell": nk,
            "monocyte": mono,
        })

fieldnames = [
    "project", "subject", "condition", "age", "sex", "treatment", "response",
    "sample", "sample_type", "time_from_treatment_start",
    "b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte",
]

with open("cell-count.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

print(f"Wrote cell-count.csv with {len(rows)} sample rows.")
