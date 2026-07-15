import sqlite3
from pathlib import Path
from shutil import copy2

import pandas as pd


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
BACKUP_PATH = Path("db/metadata_before_isic_import.db")

if not BACKUP_PATH.exists():
    copy2(DB_PATH, BACKUP_PATH)
    print(f"Backup created: {BACKUP_PATH}")
else:
    print(f"Backup already exists: {BACKUP_PATH}")


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()


# --------------------------------------------------
# 1. Create ISIC sections table
# --------------------------------------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS isic_sections (
    section_code TEXT PRIMARY KEY,
    section_title TEXT NOT NULL
)
""")


# --------------------------------------------------
# 2. Create ISIC divisions table
# --------------------------------------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS isic_divisions (
    division_code TEXT PRIMARY KEY,
    section_code TEXT NOT NULL,
    division_number INTEGER NOT NULL,
    division_title TEXT NOT NULL,
    FOREIGN KEY (section_code) REFERENCES isic_sections(section_code)
)
""")


# Clear old rows if script is run again
cur.execute("DELETE FROM isic_divisions")
cur.execute("DELETE FROM isic_sections")


# --------------------------------------------------
# 3. Read ISIC sections from Excel sheet ISIC5
# --------------------------------------------------
isic_df = pd.read_excel(EXCEL_PATH, sheet_name="ISIC5")

# Sections are rows where code is one letter: A, B, C, ...
sections_df = isic_df[
    isic_df["ISIC Rev 5 Code (with Section)"].astype(str).str.match(r"^[A-Z]$")
].copy()

for _, row in sections_df.iterrows():
    section_code = str(row["ISIC Rev 5 Code (with Section)"]).strip()
    section_title = str(row["ISIC Rev 5 Title"]).strip()

    cur.execute("""
        INSERT INTO isic_sections (section_code, section_title)
        VALUES (?, ?)
    """, (section_code, section_title))


# --------------------------------------------------
# 4. Read ISIC divisions from Excel sheet Divisions
# --------------------------------------------------
divisions_df = pd.read_excel(
    EXCEL_PATH,
    sheet_name="Divisions",
    header=None,
    names=["division_code", "division_number", "division_title"]
)

for _, row in divisions_df.iterrows():
    division_code = str(row["division_code"]).strip()
    section_code = division_code[0]
    division_number = int(row["division_number"])
    division_title = str(row["division_title"]).strip()

    cur.execute("""
        INSERT INTO isic_divisions (
            division_code,
            section_code,
            division_number,
            division_title
        )
        VALUES (?, ?, ?, ?)
    """, (
        division_code,
        section_code,
        division_number,
        division_title
    ))


conn.commit()


# --------------------------------------------------
# 5. Print check results
# --------------------------------------------------
print("\nImported ISIC sections:")
cur.execute("SELECT COUNT(*) FROM isic_sections")
print(cur.fetchone()[0])

print("\nImported ISIC divisions:")
cur.execute("SELECT COUNT(*) FROM isic_divisions")
print(cur.fetchone()[0])

print("\nFirst 10 ISIC divisions:")
cur.execute("""
    SELECT division_code, division_title
    FROM isic_divisions
    ORDER BY division_code
    LIMIT 10
""")

for code, title in cur.fetchall():
    print(f"{code}: {title}")

conn.close()

print("\nStep 2 finished successfully.")