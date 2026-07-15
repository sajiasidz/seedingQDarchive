import sqlite3
from pathlib import Path
from shutil import copy2
from datetime import datetime


DB_PATH = Path("db/metadata.db")

if not DB_PATH.exists():
    raise FileNotFoundError(
        "Could not find db/metadata.db. Run this script from the main project folder."
    )


# Safety backup
BACKUP_PATH = Path("db/metadata_before_targets.db")

if not BACKUP_PATH.exists():
    copy2(DB_PATH, BACKUP_PATH)
    print(f"Backup created: {BACKUP_PATH}")
else:
    print(f"Backup already exists: {BACKUP_PATH}")


PRIMARY_DATA_EXTENSIONS = {
    "txt", "pdf", "rtf", "doc", "docx", "odt",
    "md", "html", "htm", "csv", "tsv",
    "jpg", "jpeg", "png", "tif", "tiff"
}

PROJECT_TYPES_TO_CLASSIFY = {
    "QDA_PROJECT",
    "QD_PROJECT"
}


def clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").replace("\r", " ").split())


def get_keywords(cur, project_id):
    cur.execute(
        "SELECT keyword FROM keywords WHERE project_id = ?",
        (project_id,)
    )
    return [clean_text(row[0]) for row in cur.fetchall() if clean_text(row[0])]


def get_file_info(cur, project_id):
    cur.execute(
        "SELECT file_name, file_type FROM files WHERE project_id = ?",
        (project_id,)
    )
    return cur.fetchall()


def build_project_text(title, description, language, keywords, file_rows):
    file_names = []
    file_types = []

    for file_name, file_type in file_rows:
        if file_name:
            file_names.append(clean_text(file_name))
        if file_type:
            file_types.append(clean_text(file_type).lower())

    # Keep text not too huge
    file_names_text = " | ".join(file_names[:200])
    file_types_text = " ".join(sorted(set(file_types)))

    return clean_text(f"""
        Project title: {title}
        Project description: {description}
        Language: {language}
        Keywords: {"; ".join(keywords)}
        File types: {file_types_text}
        File names: {file_names_text}
    """)


def build_file_text(project_title, project_description, language, keywords, file_name, file_type):
    return clean_text(f"""
        Project title: {project_title}
        Project description: {project_description}
        Language: {language}
        Keywords: {"; ".join(keywords)}
        Primary data file name: {file_name}
        Primary data file type: {file_type}
    """)


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()


# --------------------------------------------------
# 1. Create classification_targets table
# --------------------------------------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS classification_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_level TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    file_id INTEGER,
    repository_id INTEGER NOT NULL,
    project_type TEXT NOT NULL,
    input_title TEXT,
    file_name TEXT,
    file_type TEXT,
    input_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (file_id) REFERENCES files(id)
)
""")


# Clear old targets if script is run again
cur.execute("DELETE FROM classification_targets")


# --------------------------------------------------
# 2. Prepare project-level targets
# --------------------------------------------------
cur.execute("""
    SELECT id, repository_id, project_type, title, description, language
    FROM projects
    WHERE project_type IN ('QDA_PROJECT', 'QD_PROJECT')
""")

projects = cur.fetchall()

project_target_count = 0
file_target_count = 0
created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for project_id, repository_id, project_type, title, description, language in projects:
    title = clean_text(title)
    description = clean_text(description)
    language = clean_text(language)

    keywords = get_keywords(cur, project_id)
    file_rows = get_file_info(cur, project_id)

    project_input_text = build_project_text(
        title=title,
        description=description,
        language=language,
        keywords=keywords,
        file_rows=file_rows
    )

    cur.execute("""
        INSERT INTO classification_targets (
            target_level,
            project_id,
            file_id,
            repository_id,
            project_type,
            input_title,
            file_name,
            file_type,
            input_text,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "project",
        project_id,
        None,
        repository_id,
        project_type,
        title,
        None,
        None,
        project_input_text,
        created_at
    ))

    project_target_count += 1


    # --------------------------------------------------
    # 3. Prepare file-level targets for primary data files
    # --------------------------------------------------
    cur.execute("""
        SELECT id, file_name, file_type
        FROM files
        WHERE project_id = ?
    """, (project_id,))

    project_files = cur.fetchall()

    for file_id, file_name, file_type in project_files:
        file_name_clean = clean_text(file_name)
        file_type_clean = clean_text(file_type).lower().lstrip(".")

        if file_type_clean not in PRIMARY_DATA_EXTENSIONS:
            continue

        file_input_text = build_file_text(
            project_title=title,
            project_description=description,
            language=language,
            keywords=keywords,
            file_name=file_name_clean,
            file_type=file_type_clean
        )

        cur.execute("""
            INSERT INTO classification_targets (
                target_level,
                project_id,
                file_id,
                repository_id,
                project_type,
                input_title,
                file_name,
                file_type,
                input_text,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "file",
            project_id,
            file_id,
            repository_id,
            project_type,
            title,
            file_name_clean,
            file_type_clean,
            file_input_text,
            created_at
        ))

        file_target_count += 1


conn.commit()


# --------------------------------------------------
# 4. Print checks
# --------------------------------------------------
print("\nCreated classification targets.")

print("\nProject-level targets:")
print(project_target_count)

print("\nFile-level primary data targets:")
print(file_target_count)

print("\nTargets by repository, project type, and target level:")
cur.execute("""
    SELECT repository_id, project_type, target_level, COUNT(*)
    FROM classification_targets
    GROUP BY repository_id, project_type, target_level
    ORDER BY repository_id, project_type, target_level
""")

for repository_id, project_type, target_level, count in cur.fetchall():
    print(
        f"repository_id={repository_id} | "
        f"{project_type} | "
        f"{target_level}: {count}"
    )


print("\nExample targets:")
cur.execute("""
    SELECT target_level, project_type, input_title, file_name
    FROM classification_targets
    LIMIT 5
""")

for target_level, project_type, input_title, file_name in cur.fetchall():
    print(f"{target_level} | {project_type} | {input_title} | {file_name}")


conn.close()

print("\nStep 3 finished successfully.")