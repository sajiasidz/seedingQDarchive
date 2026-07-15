from pathlib import Path
from shutil import copy2
import sqlite3


SOURCE_DB = Path("db/metadata.db")
FINAL_DB = Path("db/23084716-sq26-classification.db")


if not SOURCE_DB.exists():
    raise FileNotFoundError(
        "Could not find db/metadata.db. Run this script from the main project folder."
    )


copy2(SOURCE_DB, FINAL_DB)
print(f"Created final database copy: {FINAL_DB}")


conn = sqlite3.connect(FINAL_DB)
cur = conn.cursor()

print("\nChecking final database tables:")

tables_to_check = [
    "projects",
    "files",
    "keywords",
    "person_role",
    "licenses",
    "isic_sections",
    "isic_divisions",
    "classification_targets",
    "classification_results",
]

for table in tables_to_check:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"{table}: {count}")

conn.close()

print("\nStep 6 finished successfully.")