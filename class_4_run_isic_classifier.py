import hashlib
import sqlite3
from pathlib import Path
from shutil import copy2
from datetime import datetime

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


DB_PATH = Path("db/metadata.db")
EXCEL_PATH = Path("ISIC5_Exp_Notes.xlsx")

if not DB_PATH.exists():
    raise FileNotFoundError(
        "Could not find db/metadata.db. Run this script from the main project folder."
    )

if not EXCEL_PATH.exists():
    raise FileNotFoundError(
        "Could not find ISIC5_Exp_Notes.xlsx. Put it in the main project folder."
    )


# Safety backup
BACKUP_PATH = Path("db/metadata_before_isic_classification.db")

if not BACKUP_PATH.exists():
    copy2(DB_PATH, BACKUP_PATH)
    print(f"Backup created: {BACKUP_PATH}")
else:
    print(f"Backup already exists: {BACKUP_PATH}")


CLASSIFIER_VERSION = "tfidf_isic5_division_v1"
BATCH_SIZE = 3000


def clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").replace("\r", " ").split())


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def load_isic_division_documents():
    """
    Reads ISIC Rev. 5 division-level rows from the Excel file.
    Division rows look like A01, A02, B05, C10, etc.
    """
    df = pd.read_excel(EXCEL_PATH, sheet_name="ISIC5")

    code_col = "ISIC Rev 5 Code (with Section)"
    title_col = "ISIC Rev 5 Title"

    text_columns = [
        "ISIC Rev 5 Title",
        "ISIC Rev 5 Introductory Text",
        "ISIC Rev 5 Includes",
        "ISIC Rev 5 Includes Also",
        "ISIC Rev 5 Excludes",
    ]

    divisions = df[
        df[code_col].astype(str).str.match(r"^[A-Z][0-9]{2}$", na=False)
    ].copy()

    documents = []

    for _, row in divisions.iterrows():
        division_code = clean_text(row[code_col])
        division_title = clean_text(row[title_col])
        section_code = division_code[0]

        parts = []
        for col in text_columns:
            if col in divisions.columns:
                value = clean_text(row.get(col, ""))
                if value and value.lower() != "nan":
                    parts.append(value)

        division_text = clean_text(" ".join(parts))

        documents.append({
            "division_code": division_code,
            "section_code": section_code,
            "division_title": division_title,
            "division_text": division_text,
        })

    return documents


def choose_secondary(primary_score, secondary_score, secondary_code, secondary_title):
    """
    Secondary class is saved only if it is reasonably close to the primary class.
    Otherwise, it stays empty.
    """
    if secondary_score >= 0.05 and secondary_score >= (primary_score * 0.75):
        return secondary_code, secondary_title

    return "", ""


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()


# --------------------------------------------------
# 1. Create results table
# --------------------------------------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS classification_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    target_level TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    file_id INTEGER,
    repository_id INTEGER NOT NULL,
    project_type TEXT NOT NULL,

    primary_class TEXT NOT NULL,
    primary_class_name TEXT NOT NULL,
    primary_score REAL NOT NULL,

    secondary_class TEXT,
    secondary_class_name TEXT,
    secondary_score REAL,

    classifier_version TEXT NOT NULL,
    input_text_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,

    FOREIGN KEY (target_id) REFERENCES classification_targets(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (file_id) REFERENCES files(id)
)
""")


# Clear previous results for this classifier version
cur.execute(
    "DELETE FROM classification_results WHERE classifier_version = ?",
    (CLASSIFIER_VERSION,)
)


# --------------------------------------------------
# 2. Load ISIC division documents
# --------------------------------------------------
isic_docs = load_isic_division_documents()

if not isic_docs:
    raise RuntimeError("No ISIC division documents were loaded.")

isic_codes = [doc["division_code"] for doc in isic_docs]
isic_titles = [doc["division_title"] for doc in isic_docs]
isic_texts = [doc["division_text"] for doc in isic_docs]

print(f"\nLoaded ISIC division classes: {len(isic_docs)}")


# --------------------------------------------------
# 3. Load classification targets
# --------------------------------------------------
targets_df = pd.read_sql_query("""
    SELECT
        id AS target_id,
        target_level,
        project_id,
        file_id,
        repository_id,
        project_type,
        input_text
    FROM classification_targets
    ORDER BY id
""", conn)

if targets_df.empty:
    raise RuntimeError(
        "classification_targets table is empty. Run step 3 first."
    )

targets_df["input_text"] = targets_df["input_text"].fillna("").map(clean_text)

print(f"Loaded classification targets: {len(targets_df)}")


# --------------------------------------------------
# 4. TF-IDF vectorization
# --------------------------------------------------
print("\nBuilding TF-IDF model...")

all_texts = isic_texts + targets_df["input_text"].tolist()

vectorizer = TfidfVectorizer(
    lowercase=True,
    stop_words="english",
    ngram_range=(1, 2),
    min_df=1,
    max_df=0.95
)

all_matrix = vectorizer.fit_transform(all_texts)

isic_matrix = all_matrix[:len(isic_texts)]
target_matrix = all_matrix[len(isic_texts):]

print("TF-IDF model ready.")


# --------------------------------------------------
# 5. Classify targets in batches
# --------------------------------------------------
created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
insert_rows = []

print("\nClassifying targets...")

for start in range(0, len(targets_df), BATCH_SIZE):
    end = min(start + BATCH_SIZE, len(targets_df))
    batch_matrix = target_matrix[start:end]

    similarities = linear_kernel(batch_matrix, isic_matrix)

    batch_df = targets_df.iloc[start:end].reset_index(drop=True)

    for i, row in batch_df.iterrows():
        scores = similarities[i]

        ranked_indices = scores.argsort()[::-1]

        primary_idx = ranked_indices[0]
        secondary_idx = ranked_indices[1]

        primary_code = isic_codes[primary_idx]
        primary_title = isic_titles[primary_idx]
        primary_score = float(scores[primary_idx])

        raw_secondary_code = isic_codes[secondary_idx]
        raw_secondary_title = isic_titles[secondary_idx]
        secondary_score = float(scores[secondary_idx])

        secondary_code, secondary_title = choose_secondary(
            primary_score=primary_score,
            secondary_score=secondary_score,
            secondary_code=raw_secondary_code,
            secondary_title=raw_secondary_title
        )

        input_text = row["input_text"]

        insert_rows.append((
            int(row["target_id"]),
            row["target_level"],
            int(row["project_id"]),
            None if pd.isna(row["file_id"]) else int(row["file_id"]),
            int(row["repository_id"]),
            row["project_type"],

            primary_code,
            primary_title,
            primary_score,

            secondary_code,
            secondary_title,
            secondary_score,

            CLASSIFIER_VERSION,
            text_hash(input_text),
            created_at
        ))

    print(f"Classified {end} / {len(targets_df)} targets")


cur.executemany("""
    INSERT INTO classification_results (
        target_id,
        target_level,
        project_id,
        file_id,
        repository_id,
        project_type,

        primary_class,
        primary_class_name,
        primary_score,

        secondary_class,
        secondary_class_name,
        secondary_score,

        classifier_version,
        input_text_hash,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", insert_rows)

conn.commit()


# --------------------------------------------------
# 6. Print result checks
# --------------------------------------------------
print("\nInserted classification results:")
cur.execute("""
    SELECT COUNT(*)
    FROM classification_results
    WHERE classifier_version = ?
""", (CLASSIFIER_VERSION,))
print(cur.fetchone()[0])


print("\nResults by target level:")
cur.execute("""
    SELECT target_level, COUNT(*)
    FROM classification_results
    WHERE classifier_version = ?
    GROUP BY target_level
    ORDER BY target_level
""", (CLASSIFIER_VERSION,))

for target_level, count in cur.fetchall():
    print(f"{target_level}: {count}")


print("\nTop 20 project-level primary classes:")
cur.execute("""
    SELECT primary_class, primary_class_name, COUNT(*) AS count
    FROM classification_results
    WHERE classifier_version = ?
      AND target_level = 'project'
    GROUP BY primary_class, primary_class_name
    ORDER BY count DESC
    LIMIT 20
""", (CLASSIFIER_VERSION,))

for code, name, count in cur.fetchall():
    print(f"{code} | {name}: {count}")


print("\nExample project classifications:")
cur.execute("""
    SELECT
        p.title,
        p.project_type,
        r.primary_class,
        r.primary_class_name,
        ROUND(r.primary_score, 4),
        r.secondary_class,
        r.secondary_class_name,
        ROUND(r.secondary_score, 4)
    FROM classification_results r
    JOIN projects p ON p.id = r.project_id
    WHERE r.classifier_version = ?
      AND r.target_level = 'project'
    LIMIT 10
""", (CLASSIFIER_VERSION,))

for row in cur.fetchall():
    title, project_type, p_class, p_name, p_score, s_class, s_name, s_score = row
    print(
        f"{title} | {project_type} | "
        f"primary={p_class} {p_name} ({p_score}) | "
        f"secondary={s_class} {s_name} ({s_score})"
    )


conn.close()

print("\nStep 4 finished successfully.")