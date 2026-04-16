import sqlite3
from pathlib import Path
import pandas as pd

from config import DB_PATH, EXPORT_DIR


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query_string TEXT,
        repository_id INTEGER NOT NULL,
        repository_url TEXT NOT NULL,
        project_url TEXT NOT NULL UNIQUE,
        version TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        language TEXT,
        doi TEXT,
        upload_date TEXT,
        download_date TEXT NOT NULL,
        download_repository_folder TEXT NOT NULL,
        download_project_folder TEXT NOT NULL,
        download_version_folder TEXT,
        download_method TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        file_type TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        keyword TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS person_role (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        license TEXT NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects (id)
    )
    """)

    conn.commit()
    conn.close()


def insert_project(project_data: dict) -> int:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT OR IGNORE INTO projects (
        query_string, repository_id, repository_url, project_url, version,
        title, description, language, doi, upload_date, download_date,
        download_repository_folder, download_project_folder,
        download_version_folder, download_method
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        project_data.get("query_string"),
        project_data.get("repository_id"),
        project_data.get("repository_url"),
        project_data.get("project_url"),
        project_data.get("version"),
        project_data.get("title"),
        project_data.get("description"),
        project_data.get("language"),
        project_data.get("doi"),
        project_data.get("upload_date"),
        project_data.get("download_date"),
        project_data.get("download_repository_folder"),
        project_data.get("download_project_folder"),
        project_data.get("download_version_folder"),
        project_data.get("download_method"),
    ))

    conn.commit()

    cur.execute(
        "SELECT id FROM projects WHERE project_url = ?",
        (project_data.get("project_url"),)
    )
    row = cur.fetchone()

    conn.close()
    return row[0] if row else None


def insert_file(file_data: dict):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id FROM files
    WHERE project_id = ? AND file_name = ?
    """, (
        file_data.get("project_id"),
        file_data.get("file_name"),
    ))
    row = cur.fetchone()

    if row:
        cur.execute("""
        UPDATE files
        SET file_type = ?, status = ?
        WHERE id = ?
        """, (
            file_data.get("file_type"),
            file_data.get("status"),
            row[0],
        ))
    else:
        cur.execute("""
        INSERT INTO files (
            project_id, file_name, file_type, status
        )
        VALUES (?, ?, ?, ?)
        """, (
            file_data.get("project_id"),
            file_data.get("file_name"),
            file_data.get("file_type"),
            file_data.get("status"),
        ))

    conn.commit()
    conn.close()


def insert_keyword(project_id: int, keyword: str):
    if not keyword:
        return

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id FROM keywords
    WHERE project_id = ? AND keyword = ?
    """, (project_id, keyword))
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
        INSERT INTO keywords (project_id, keyword)
        VALUES (?, ?)
        """, (project_id, keyword))
        conn.commit()

    conn.close()


def insert_person_role(project_id: int, name: str, role: str):
    if not name:
        return

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id FROM person_role
    WHERE project_id = ? AND name = ? AND role = ?
    """, (project_id, name, role))
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
        INSERT INTO person_role (project_id, name, role)
        VALUES (?, ?, ?)
        """, (project_id, name, role))
        conn.commit()

    conn.close()


def insert_license(project_id: int, license_value: str):
    if not license_value:
        return

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT id FROM licenses
    WHERE project_id = ? AND license = ?
    """, (project_id, license_value))
    exists = cur.fetchone()

    if not exists:
        cur.execute("""
        INSERT INTO licenses (project_id, license)
        VALUES (?, ?)
        """, (project_id, license_value))
        conn.commit()

    conn.close()


def export_table_to_csv(table_name: str, output_path: Path):
    conn = get_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    conn.close()
    return output_path


def export_all_tables():
    tables = ["projects", "files", "keywords", "person_role", "licenses"]
    exported = []

    for table in tables:
        output_path = EXPORT_DIR / f"{table}.csv"
        export_table_to_csv(table, output_path)
        exported.append(output_path)

    return exported