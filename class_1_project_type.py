import sqlite3
from pathlib import Path
from shutil import copy2


DB_PATH = Path("db/metadata.db")

if not DB_PATH.exists():
    raise FileNotFoundError(
        "Could not find db/metadata.db. "
        "Run this script from the main project folder."
    )


# Make a safety backup first
BACKUP_PATH = Path("db/metadata_before_part2.db")

if not BACKUP_PATH.exists():
    copy2(DB_PATH, BACKUP_PATH)
    print(f"Backup created: {BACKUP_PATH}")
else:
    print(f"Backup already exists: {BACKUP_PATH}")


QDA_EXTENSIONS = {
    "qdpx", "qdc", "mqda", "nvp", "nvpx", "atlasproj",
    "hpr7", "ppj", "pprj", "qlt", "f4p", "qpd"
}

PRIMARY_DATA_EXTENSIONS = {
    "txt", "pdf", "rtf", "doc", "docx", "odt",
    "md", "html", "htm", "csv", "tsv",
    "jpg", "jpeg", "png", "tif", "tiff"
}

VALID_DATA_EXTENSIONS = QDA_EXTENSIONS | PRIMARY_DATA_EXTENSIONS | {
    "xlsx", "xls", "xml", "json", "zip",
    "sav", "dta", "por", "dat", "tab",
    "ods", "dbf"
}


def classify_project(file_types):
    file_types = {str(ft).lower().strip().lstrip(".") for ft in file_types if ft}

    if file_types & QDA_EXTENSIONS:
        return "QDA_PROJECT"

    if file_types & PRIMARY_DATA_EXTENSIONS:
        return "QD_PROJECT"

    if file_types & VALID_DATA_EXTENSIONS:
        return "OTHER_PROJECT"

    return "NOT_A_PROJECT"


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Add project_type column if it does not exist
cur.execute("PRAGMA table_info(projects)")
project_columns = [row[1] for row in cur.fetchall()]

if "project_type" not in project_columns:
    cur.execute("ALTER TABLE projects ADD COLUMN project_type TEXT")
    print("Added column: projects.project_type")
else:
    print("Column already exists: projects.project_type")


# Get all projects
cur.execute("SELECT id FROM projects")
project_ids = [row[0] for row in cur.fetchall()]

for project_id in project_ids:
    cur.execute(
        "SELECT file_type FROM files WHERE project_id = ?",
        (project_id,)
    )
    file_types = [row[0] for row in cur.fetchall()]

    project_type = classify_project(file_types)

    cur.execute(
        "UPDATE projects SET project_type = ? WHERE id = ?",
        (project_type, project_id)
    )

conn.commit()


print("\nProject type distribution:")
cur.execute("""
    SELECT repository_id, project_type, COUNT(*)
    FROM projects
    GROUP BY repository_id, project_type
    ORDER BY repository_id, project_type
""")

for repository_id, project_type, count in cur.fetchall():
    print(f"repository_id={repository_id} | {project_type}: {count}")


print("\nTotal distribution:")
cur.execute("""
    SELECT project_type, COUNT(*)
    FROM projects
    GROUP BY project_type
    ORDER BY COUNT(*) DESC
""")

for project_type, count in cur.fetchall():
    print(f"{project_type}: {count}")

conn.close()

print("\nStep 1 finished successfully.")