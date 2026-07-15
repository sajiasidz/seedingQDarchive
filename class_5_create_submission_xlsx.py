import sqlite3
from pathlib import Path

import pandas as pd


DB_PATH = Path("db/metadata.db")
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)

OUTPUT_XLSX = EXPORT_DIR / "23084716-sq26-classification-table.xlsx"

CLASSIFIER_VERSION = "tfidf_isic5_division_v1"


if not DB_PATH.exists():
    raise FileNotFoundError(
        "Could not find db/metadata.db. Run this script from the main project folder."
    )


conn = sqlite3.connect(DB_PATH)


query = """
SELECT
    p.repository_id AS repository_id,
    p.project_type AS project_type,
    p.title AS project_title,

    CASE
        WHEN r.primary_class IS NULL
        THEN ''
        ELSE r.primary_class || ' - ' || r.primary_class_name
    END AS primary_class,

    CASE
        WHEN r.secondary_class IS NULL OR r.secondary_class = ''
        THEN ''
        ELSE r.secondary_class || ' - ' || r.secondary_class_name
    END AS secondary_class,

    COUNT(f.id) AS no_project_files

FROM projects p

LEFT JOIN classification_results r
    ON r.project_id = p.id
   AND r.classifier_version = ?
   AND r.target_level = 'project'

LEFT JOIN files f
    ON f.project_id = p.id

GROUP BY
    p.id,
    p.repository_id,
    p.project_type,
    p.title,
    r.primary_class,
    r.primary_class_name,
    r.secondary_class,
    r.secondary_class_name

ORDER BY
    p.repository_id,
    p.project_type,
    p.title
"""

df = pd.read_sql_query(query, conn, params=(CLASSIFIER_VERSION,))
conn.close()


df.to_excel(OUTPUT_XLSX, index=False)


print(f"Created corrected XLSX file: {OUTPUT_XLSX}")
print(f"Rows: {len(df)}")

print("\nRows by repository:")
print(df["repository_id"].value_counts().sort_index().to_string())

print("\nRows by repository and project type:")
print(
    df.groupby(["repository_id", "project_type"])
      .size()
      .to_string()
)

print("\nPreview of repository_id=15:")
print(
    df[df["repository_id"] == 15]
    .head(10)
    .to_string(index=False)
)

print("\nCorrected Step 5 finished successfully.")