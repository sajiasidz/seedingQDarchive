from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from config import (
    DANS_BASE_URL,
    DANS_REPOSITORY_ID,
    DANS_REPOSITORY_URL,
    DANS_DIR,
    EXPORT_DIR,
    REQUEST_TIMEOUT,
    USER_AGENT,
    QDA_EXTENSIONS,
    PRIMARY_DATA_EXTENSIONS,
    EXCLUDED_EXTENSIONS,
    MAX_FILE_SIZE_MB,
    DANS_FILE_SEARCH_TERMS,
    DANS_DATASET_SEARCH_TERMS,
)
from database import (
    insert_project,
    insert_file,
    insert_keyword,
    insert_person_role,
    insert_license,
)
from downloader import download_file, sanitize_filename


def get_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def project_page_from_pid(pid: str) -> str:
    return f"{DANS_BASE_URL}/dataset.xhtml?persistentId={quote(pid, safe='')}"


def safe_pid_folder_name(pid: str) -> str:
    return sanitize_filename(pid.replace(":", "_").replace("/", "_"))


def bytes_to_mb(num_bytes: int) -> float:
    return round((num_bytes or 0) / (1024 * 1024), 2)


def is_audio_or_video(filename: str, content_type: str = "") -> bool:
    ext = Path(filename).suffix.lower()
    ct = (content_type or "").lower()

    if ext in EXCLUDED_EXTENSIONS:
        return True
    if ct.startswith("audio/") or ct.startswith("video/"):
        return True
    return False


def is_too_large(filesize_bytes: int, max_file_size_mb: float) -> bool:
    return bytes_to_mb(filesize_bytes) > max_file_size_mb


def classify_file(filename: str) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()

    if ext in QDA_EXTENSIONS:
        return ext, "qda"
    if ext in PRIMARY_DATA_EXTENSIONS:
        return ext, "primary"
    return ext, "additional"


def search_api(session: requests.Session, query: str, item_type: str, start: int = 0, per_page: int = 100):
    url = f"{DANS_BASE_URL}/api/search"
    params = {
        "q": query,
        "type": item_type,
        "per_page": per_page,
        "start": start,
        "sort": "date",
        "order": "desc",
        "show_api_urls": "true",
    }
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()

def search_all_items(session: requests.Session, query: str, item_type: str, per_page: int = 100):
    start = 0
    all_items = []

    while True:
        payload = search_api(
            session=session,
            query=query,
            item_type=item_type,
            start=start,
            per_page=per_page,
        )
        items = payload.get("data", {}).get("items", [])

        if not items:
            break

        all_items.extend(items)

        if len(items) < per_page:
            break

        start += per_page

    return all_items

def collect_dans_candidates(per_page: int = 100) -> pd.DataFrame:
    session = get_session()
    candidates = {}

    for query in DANS_FILE_SEARCH_TERMS:
        print(f"Searching DANS file results for: {query}")
        items = search_all_items(session, query=query, item_type="file", per_page=per_page)

        for item in items:
            pid = item.get("dataset_persistent_id")
            if not pid:
                continue

            if pid not in candidates:
                candidates[pid] = {
                    "query_string": query,
                    "match_source": "file_search",
                    "dataset_pid": pid,
                    "project_url": project_page_from_pid(pid),
                    "title": item.get("dataset_name") or item.get("name") or "",
                    "description": "",
                    "published_at": item.get("published_at") or item.get("releaseOrCreateDate") or "",
                }

    for query in DANS_DATASET_SEARCH_TERMS:
        print(f"Searching DANS dataset results for: {query}")
        items = search_all_items(session, query=query, item_type="dataset", per_page=per_page)

        for item in items:
            pid = item.get("global_id")
            if not pid:
                continue

            existing = candidates.get(pid, {})
            candidates[pid] = {
                "query_string": existing.get("query_string", query),
                "match_source": existing.get("match_source", "dataset_search"),
                "dataset_pid": pid,
                "project_url": project_page_from_pid(pid),
                "title": item.get("name") or existing.get("title", ""),
                "description": item.get("description") or existing.get("description", ""),
                "published_at": item.get("published_at") or item.get("releaseOrCreateDate") or existing.get("published_at", ""),
            }

    if not candidates:
        df = pd.DataFrame(columns=[
            "query_string", "match_source", "dataset_pid", "project_url",
            "title", "description", "published_at"
        ])
    else:
        df = pd.DataFrame(
            sorted(candidates.values(), key=lambda x: (x["published_at"], x["title"]), reverse=True)
        )

    output_path = EXPORT_DIR / "dans_candidates.csv"
    df.to_csv(output_path, index=False)
    print(f"Saved {len(df)} DANS candidates to: {output_path}")
    return df


def fetch_dataset_version(session: requests.Session, pid: str) -> dict:
    url = f"{DANS_BASE_URL}/api/datasets/:persistentId/versions/:latest-published"
    response = session.get(url, params={"persistentId": pid}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_field(fields: list, type_name: str):
    for field in fields:
        if field.get("typeName") == type_name:
            return field
    return None


def primitive_value(field) -> str:
    if not field:
        return ""
    value = field.get("value")
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v is not None)
    return str(value) if value is not None else ""


def extract_compound_list(field, key_name: str) -> list[str]:
    values = []
    if not field:
        return values

    for item in field.get("value", []):
        node = item.get(key_name)
        if node and node.get("value"):
            values.append(str(node["value"]).strip())

    return values


def extract_description(field) -> str:
    if not field:
        return ""

    parts = []
    for item in field.get("value", []):
        node = item.get("dsDescriptionValue")
        if node and node.get("value"):
            parts.append(str(node["value"]).strip())

    return "\n".join(parts)


def parse_dataset_metadata(payload: dict, pid: str) -> dict:
    data = payload.get("data", {})
    version = data if "metadataBlocks" in data else data.get("latestVersion", {})
    fields = version.get("metadataBlocks", {}).get("citation", {}).get("fields", [])

    title = primitive_value(get_field(fields, "title"))
    description = extract_description(get_field(fields, "dsDescription"))
    language = primitive_value(get_field(fields, "language"))

    subject_field = get_field(fields, "subject")
    subjects = subject_field.get("value", []) if subject_field and isinstance(subject_field.get("value"), list) else []

    keyword_field = get_field(fields, "keyword")
    keywords = extract_compound_list(keyword_field, "keywordValue")

    author_field = get_field(fields, "author")
    authors = extract_compound_list(author_field, "authorName")

    files = version.get("files", [])
    version_number = f'{version.get("versionNumber", "")}.{version.get("versionMinorNumber", "")}'.strip(".")

    license_name = ""
    license_url = ""
    terms_of_use = version.get("termsOfUse") or ""

    license_obj = data.get("license") or version.get("license") or {}
    if isinstance(license_obj, dict):
        license_name = license_obj.get("name", "") or ""
        license_url = license_obj.get("uri", "") or ""

    return {
        "pid": pid,
        "title": title,
        "description": description,
        "language": language,
        "subjects": subjects,
        "keywords": keywords,
        "authors": authors,
        "files": files,
        "version": version_number,
        "published_at": version.get("releaseTime") or version.get("createTime") or "",
        "license_name": license_name,
        "license_url": license_url,
        "terms_of_use": terms_of_use,
    }


def download_dans_file(session: requests.Session, file_id: int, destination: Path):
    file_url = f"{DANS_BASE_URL}/api/access/datafile/{file_id}"
    return download_file(file_url, destination, session=session)


def ingest_dataset(pid: str, query_string: str = "", download_files: bool = True, max_file_size_mb: float = MAX_FILE_SIZE_MB):
    session = get_session()
    payload = fetch_dataset_version(session, pid)
    metadata = parse_dataset_metadata(payload, pid)

    project_folder = DANS_DIR / safe_pid_folder_name(pid)
    project_folder.mkdir(parents=True, exist_ok=True)

    project_data = {
        "query_string": query_string,
        "repository_id": DANS_REPOSITORY_ID,
        "repository_url": DANS_REPOSITORY_URL,
        "project_url": project_page_from_pid(pid),
        "version": metadata["version"],
        "title": metadata["title"] or "Untitled",
        "description": metadata["description"] or "",
        "language": metadata["language"],
        "doi": pid,
        "upload_date": metadata["published_at"],
        "download_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "download_repository_folder": "dans",
        "download_project_folder": safe_pid_folder_name(pid),
        "download_version_folder": f"version_{metadata['version']}" if metadata["version"] else "",
        "download_method": "API-CALL",
    }

    project_id = insert_project(project_data)

    for kw in metadata["subjects"]:
        insert_keyword(project_id, kw)

    for kw in metadata["keywords"]:
        insert_keyword(project_id, kw)

    for author in metadata["authors"]:
        insert_person_role(project_id, author, "UNKNOWN")

    license_value = metadata["license_name"] or metadata["license_url"] or metadata["terms_of_use"]
    if license_value:
        insert_license(project_id, license_value)

    downloaded_count = 0
    skipped_existing_count = 0
    skipped_audio_video_count = 0
    skipped_large_count = 0
    restricted_count = 0
    failed_count = 0

    for item in metadata["files"]:
        data_file = item.get("dataFile", {})

        file_id = data_file.get("id")
        file_name = data_file.get("filename") or item.get("label") or "unknown_file"
        content_type = data_file.get("contentType") or ""
        filesize_bytes = int(data_file.get("filesize", 0) or 0)

        ext, _ = classify_file(file_name)
        local_path = project_folder / sanitize_filename(file_name)

        if item.get("restricted"):
            status = "restricted"
            restricted_count += 1

        elif is_audio_or_video(file_name, content_type):
            status = "skipped_audio_video"
            skipped_audio_video_count += 1

        elif is_too_large(filesize_bytes, max_file_size_mb):
            status = "skipped_too_large"
            skipped_large_count += 1

        elif local_path.exists() and local_path.is_file() and local_path.stat().st_size > 0:
            status = "already_downloaded"
            skipped_existing_count += 1

        elif download_files and file_id:
            try:
                download_dans_file(session, file_id, local_path)
                status = "downloaded"
                downloaded_count += 1
            except Exception as e:
                status = f"download_failed: {e}"
                failed_count += 1

        else:
            status = "metadata_collected"

        insert_file({
            "project_id": project_id,
            "file_name": file_name,
            "file_type": ext.lstrip(".") if ext else "unknown",
            "status": status,
        })

    print(f"Ingested DANS dataset: {metadata['title']}")
    print(
        f"downloaded={downloaded_count}, "
        f"already_downloaded={skipped_existing_count}, "
        f"skipped_audio_video={skipped_audio_video_count}, "
        f"skipped_too_large={skipped_large_count}, "
        f"restricted={restricted_count}, "
        f"failed={failed_count}"
    )


def ingest_from_csv(csv_path: str, limit: int | None = None, download_files: bool = True, max_file_size_mb: float = MAX_FILE_SIZE_MB):
    df = pd.read_csv(csv_path)

    if "dataset_pid" not in df.columns:
        raise ValueError("CSV must contain a 'dataset_pid' column.")

    df = df.drop_duplicates(subset=["dataset_pid"])

    if limit is not None:
        df = df.head(limit)

    total = len(df)
    print(f"Total DANS datasets to process: {total}")

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        pid = str(row["dataset_pid"]).strip()
        query_string = str(row.get("query_string", "")).strip()

        print(f"\n[{idx}/{total}] Processing {pid}")

        try:
            ingest_dataset(
                pid=pid,
                query_string=query_string,
                download_files=download_files,
                max_file_size_mb=max_file_size_mb,
            )
        except Exception as e:
            print(f"FAILED for {pid}: {e}")