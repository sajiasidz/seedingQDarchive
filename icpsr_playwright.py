import argparse
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from playwright.sync_api import sync_playwright

from config import (
    ICPSR_BASE_URL,
    ICPSR_REPOSITORY_ID,
    ICPSR_REPOSITORY_URL,
    ICPSR_DIR,
    ICPSR_PROFILE_DIR,
    ICPSR_SERIES_URL,
    ICPSR_SEARCH_TERMS,
    ICPSR_MAX_FILE_SIZE_MB,
    ICPSR_MAX_PAGES_PER_QUERY,
    EXCLUDED_EXTENSIONS,
    USER_AGENT,
)
from database import (
    init_db,
    insert_project,
    insert_file,
    insert_keyword,
    insert_person_role,
    insert_license,
    export_all_tables,
)

ALLOWED_TEXT_EXTENSIONS = {
    ".txt", ".pdf", ".rtf", ".doc", ".docx", ".odt",
    ".csv", ".tsv", ".xlsx", ".xls", ".xml", ".json",
    ".qdpx", ".qdc", ".mqda", ".nvp", ".nvpx", ".atlasproj",
    ".hpr7", ".ppj", ".pprj", ".qlt", ".f4p", ".qpd",
    ".zip",
}

SKIP_HREF_PATTERNS = [
    "twitter.com",
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "mailto:",
    "/variables",
    "/publications",
    "endnote",
    "ris",
    "exportcitation",
]


def normalize_study_url(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"(https?://[^/]+/web/ICPSR/studies/\d+)", url, re.I)
    return match.group(1) if match else url


def study_id_from_url(url: str) -> str:
    match = re.search(r"/studies/(\d+)", url)
    return match.group(1) if match else "unknown_study"


def sanitize_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:220] if name else "downloaded_file"


def file_ext_from_name(name: str) -> str:
    return Path(name).suffix.lower()


def is_audio_or_video(filename: str, content_type: str = "") -> bool:
    ext = file_ext_from_name(filename)
    ct = (content_type or "").lower()

    if ext in EXCLUDED_EXTENSIONS:
        return True
    if ct.startswith("audio/") or ct.startswith("video/"):
        return True
    return False


def is_too_large(num_bytes: int, max_mb: float) -> bool:
    return (num_bytes or 0) > int(max_mb * 1024 * 1024)


def simplified_file_type(filename: str, content_type: str) -> str:
    ext = file_ext_from_name(filename)
    if ext:
        return ext.lstrip(".")
    if content_type and "/" in content_type:
        return content_type.split("/")[-1]
    return "unknown"


def safe_goto(page, url: str, timeout: int = 60000, retries: int = 3) -> bool:
    last_error = None

    for attempt in range(retries):
        try:
            page.goto(url, wait_until="commit", timeout=timeout)
            page.wait_for_timeout(5000)
            return True
        except Exception as e:
            last_error = e
            print(f"Goto failed ({attempt + 1}/{retries}) for {url}: {e}")
            page.wait_for_timeout(3000)

    print(f"Skipping URL after repeated failures: {url}")
    if last_error:
        print(f"Last error: {last_error}")
    return False


def page_has_service_unavailable(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
        return "service unavailable" in text or "503" in text
    except Exception:
        return False


def page_is_likely_qualitative(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=8000).lower()
    except Exception:
        return False

    positive_terms = [
        "qualitative",
        "interview",
        "focus group",
        "transcript",
        "ethnographic",
        "in-depth interview",
    ]
    return any(term in text for term in positive_terms)


def page_is_restricted(page) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=8000).lower()
    except Exception:
        return False

    restricted_terms = [
        "restricted data use agreement",
        "access to these data is restricted",
        "restricted",
        "irb approval",
    ]
    return any(term in text for term in restricted_terms)


def launch_context(headless: bool = False):
    p = sync_playwright().start()
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(ICPSR_PROFILE_DIR),
        headless=headless,
        accept_downloads=True,
        downloads_path=str(ICPSR_DIR),
    )
    return p, context


def ensure_login(context):
    page = context.new_page()
    safe_goto(page, "https://www.icpsr.umich.edu/", timeout=60000, retries=2)

    try:
        text = page.locator("body").inner_text(timeout=10000)
    except Exception:
        text = ""

    if "Log In" in text and "Log Out" not in text:
        print("\nICPSR login needed.")
        print("A browser window is open.")
        print("Please log in with your university account, then press Enter here.")
        input()
        safe_goto(page, "https://www.icpsr.umich.edu/", timeout=60000, retries=2)

    print("Login session ready.")
    page.close()


def build_requests_session_from_context(context):
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for cookie in context.cookies():
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )

    return session


def collect_study_links_from_page(page) -> set[str]:
    urls = set()
    anchors = page.locator("a[href*='/web/ICPSR/studies/']")
    count = anchors.count()

    for i in range(count):
        try:
            href = anchors.nth(i).get_attribute("href")
        except Exception:
            href = None

        if not href:
            continue

        full = normalize_study_url(urljoin(page.url, href))
        if "/web/ICPSR/studies/" in full and re.search(r"/studies/\d+$", full):
            urls.add(full)

    return urls


def get_next_page(page):
    selectors = [
        "button[aria-label*='Next']",
        "a[aria-label*='Next']",
        "text=Next",
    ]

    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                return loc
        except Exception:
            pass

    return None


def open_data_documentation_tab(page):
    selectors = [
        "a:has-text('Data & Documentation')",
        "button:has-text('Data & Documentation')",
        "text=Data & Documentation",
        "a:has-text('Data')",
        "button:has-text('Data')",
        "a:has-text('Documentation')",
        "button:has-text('Documentation')",
    ]

    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                loc.click(timeout=3000)
                page.wait_for_timeout(3000)
                return True
        except Exception:
            pass

    return False


def collect_qds_series_results(context) -> list[str]:
    page = context.new_page()
    print("\nCollecting QDS series studies...")

    ok = safe_goto(page, ICPSR_SERIES_URL, timeout=60000, retries=2)
    if not ok:
        print("QDS series page could not be loaded. Skipping QDS series.")
        page.close()
        return []

    if page_has_service_unavailable(page):
        print("QDS series returned Service Unavailable. Skipping QDS series.")
        page.close()
        return []

    selectors = [
        "a:has-text('Studies')",
        "button:has-text('Studies')",
        "text=Studies",
    ]

    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=3000)
            page.wait_for_timeout(3000)
            break
        except Exception:
            pass

    urls = sorted(collect_study_links_from_page(page))
    print(f"  QDS series: {len(urls)} study links")
    page.close()
    return urls


def collect_search_results(context, query: str, max_pages: int = 10) -> list[str]:
    page = context.new_page()
    search_url = f"{ICPSR_BASE_URL}/web/ICPSR/search/studies?q={quote_plus(query)}"
    print(f"\nSearching ICPSR for: {query}")

    ok = safe_goto(page, search_url, timeout=90000, retries=3)
    if not ok:
        print(f"Search page failed for query: {query}")
        page.close()
        return []

    if page_has_service_unavailable(page):
        print(f"Service Unavailable on search page for query: {query}")
        page.close()
        return []

    urls = set()

    for page_no in range(1, max_pages + 1):
        page.wait_for_timeout(4000)
        found = collect_study_links_from_page(page)
        urls.update(found)
        print(f"  page {page_no}: +{len(found)} study links (total {len(urls)})")

        nxt = get_next_page(page)
        if not nxt:
            break

        try:
            nxt.click(timeout=5000)
            page.wait_for_timeout(7000)

            if page_has_service_unavailable(page):
                print("  next page returned Service Unavailable, stopping this query.")
                break
        except Exception:
            break

    page.close()
    return sorted(urls)


def extract_block(text: str, start_label: str, end_labels: list[str]) -> str:
    start_idx = text.find(start_label)
    if start_idx == -1:
        return ""

    start_idx += len(start_label)
    end_positions = [text.find(label, start_idx) for label in end_labels if text.find(label, start_idx) != -1]
    end_idx = min(end_positions) if end_positions else len(text)

    block = text[start_idx:end_idx].strip()
    block = re.sub(r"\n{2,}", "\n", block)
    return block.strip()


def split_people(block: str) -> list[str]:
    if not block:
        return []
    lines = [x.strip(" •\t") for x in block.splitlines()]
    lines = [x for x in lines if x]
    cleaned = []
    for line in lines:
        if len(line) > 2 and not line.lower().startswith("view help"):
            cleaned.append(line)
    return cleaned


def split_keywords(block: str) -> list[str]:
    if not block:
        return []
    parts = re.split(r"[\n;]+| {2,}| \u00a0 ", block)
    out = []
    for p in parts:
        p = p.replace("\u00a0", " ").strip(" •\t")
        if p:
            out.append(p)
    return out


def extract_study_metadata(page, study_url: str, query_string: str) -> dict:
    ok = safe_goto(page, study_url, timeout=60000, retries=2)
    if not ok:
        raise RuntimeError(f"Could not open study page: {study_url}")

    if page_has_service_unavailable(page):
        raise RuntimeError(f"Service unavailable page for: {study_url}")

    if not page_is_likely_qualitative(page):
        raise RuntimeError(f"Not a strong qualitative candidate: {study_url}")

    body_text = page.locator("body").inner_text(timeout=15000)

    try:
        title = page.locator("h1").first.inner_text(timeout=5000).strip()
    except Exception:
        title = page.title().strip()

    title = re.sub(r"\s+", " ", title)
    sid = study_id_from_url(study_url)

    doi_match = re.search(r"(10\.\d{4,9}/ICPSR\d+(?:\.v\d+)?)", body_text, re.I)
    doi = doi_match.group(1) if doi_match else ""

    version_match = re.search(r"Version Date:\s*(.+)", body_text)
    version = version_match.group(1).strip() if version_match else ""

    description = extract_block(
        body_text,
        "Summary",
        [
            "Citation",
            "Subject Terms",
            "Geographic Coverage",
            "Restrictions",
            "Distributor(s)",
            "Scope of Project",
            "Methodology",
            "Version(s)",
            "Notes",
        ],
    )

    subject_terms = extract_block(
        body_text,
        "Subject Terms",
        ["Geographic Coverage", "Restrictions", "Distributor(s)", "Scope of Project", "Methodology", "Version(s)"],
    )

    principal_investigators = extract_block(
        body_text,
        "Principal Investigator(s):",
        ["https://doi.org/", "Version V", "Analyze Online", "Project Description", "Summary"],
    )

    upload_date = ""
    original_release = extract_block(body_text, "Original Release Date", ["Version History", "Notes", "Methodology"])
    if original_release:
        upload_date = original_release.splitlines()[0].strip()
    elif version:
        upload_date = version

    language = ""
    if re.search(r"\bEnglish\b", body_text, re.I):
        language = "English"

    authors = split_people(principal_investigators)
    keywords = split_keywords(subject_terms)

    return {
        "query_string": query_string,
        "study_id": sid,
        "project_url": study_url,
        "version": version,
        "title": title or f"ICPSR {sid}",
        "description": description or "",
        "language": language,
        "doi": doi,
        "upload_date": upload_date,
        "download_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "download_repository_folder": "icpsr_private",
        "download_project_folder": sid,
        "download_version_folder": "",
        "download_method": "PLAYWRIGHT+REQUESTS",
        "keywords": keywords,
        "authors": authors,
        "license": "ICPSR terms - internal use only",
    }


def get_candidate_file_links(page) -> list[str]:
    hrefs = set()

    anchors = page.locator("a[href]")
    count = anchors.count()

    for i in range(count):
        try:
            href = anchors.nth(i).get_attribute("href")
            text = anchors.nth(i).inner_text(timeout=1000).strip().lower()
        except Exception:
            href = None
            text = ""

        if not href:
            continue

        full = urljoin(page.url, href)
        lower_full = full.lower()

        if any(pattern in lower_full for pattern in SKIP_HREF_PATTERNS):
            continue

        parsed = urlparse(full)
        ext = Path(parsed.path).suffix.lower()

        if ext in EXCLUDED_EXTENSIONS:
            continue

        if ext in ALLOWED_TEXT_EXTENSIONS:
            hrefs.add(full)
            continue

        if "download" in text or "download" in lower_full:
            hrefs.add(full)

    return sorted(hrefs)


def filename_from_response(response: requests.Response, url: str) -> str:
    content_disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition, re.I)
    if match:
        return sanitize_filename(match.group(1))

    path_name = Path(urlparse(response.url).path).name or Path(urlparse(url).path).name
    return sanitize_filename(path_name or "downloaded_file")


def download_file_if_allowed(session: requests.Session, url: str, destination_dir: Path, max_file_size_mb: float):
    with session.get(url, stream=True, allow_redirects=True, timeout=180) as response:
        response.raise_for_status()

        content_type = (response.headers.get("content-type") or "").lower()
        content_length = int(response.headers.get("content-length", "0") or 0)

        filename = filename_from_response(response, url)
        ext = file_ext_from_name(filename)

        if is_audio_or_video(filename, content_type):
            return {
                "file_name": filename,
                "file_type": simplified_file_type(filename, content_type),
                "status": "skipped_audio_video",
            }

        if content_length and is_too_large(content_length, max_file_size_mb):
            return {
                "file_name": filename,
                "file_type": simplified_file_type(filename, content_type),
                "status": "skipped_too_large",
            }

        if "text/html" in content_type and ext not in ALLOWED_TEXT_EXTENSIONS:
            return {
                "file_name": filename,
                "file_type": simplified_file_type(filename, content_type),
                "status": "not_a_file",
            }

        destination = destination_dir / filename
        if destination.exists() and destination.stat().st_size > 0:
            return {
                "file_name": filename,
                "file_type": simplified_file_type(filename, content_type),
                "status": "already_downloaded",
            }

        destination_dir.mkdir(parents=True, exist_ok=True)
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        if destination.stat().st_size > int(max_file_size_mb * 1024 * 1024):
            destination.unlink(missing_ok=True)
            return {
                "file_name": filename,
                "file_type": simplified_file_type(filename, content_type),
                "status": "skipped_too_large",
            }

        return {
            "file_name": filename,
            "file_type": simplified_file_type(filename, content_type),
            "status": "downloaded",
        }


def collect_download_controls(page):
    controls = []
    seen = set()

    keywords = [
        "download",
        "data",
        "documentation",
        "pdf",
        "rtf",
        "txt",
        "zip",
        "ascii",
        "original",
    ]

    elements = page.query_selector_all("a, button")

    for handle in elements:
        try:
            text = (handle.inner_text() or "").strip()
        except Exception:
            text = ""

        try:
            href = handle.get_attribute("href") or ""
        except Exception:
            href = ""

        label = f"{text} {href}".lower()

        if not label.strip():
            continue

        if any(pattern in label for pattern in SKIP_HREF_PATTERNS):
            continue

        if not any(keyword in label for keyword in keywords):
            continue

        key = (text[:120], href[:250])
        if key in seen:
            continue
        seen.add(key)

        controls.append({
            "handle": handle,
            "text": text,
            "href": href,
        })

    return controls


def try_playwright_downloads(page, project_folder: Path, max_file_size_mb: float):
    results = []
    controls = collect_download_controls(page)

    print(f"Download controls found: {len(controls)}")

    for idx, control in enumerate(controls, start=1):
        handle = control["handle"]
        label = control["text"] or control["href"] or f"control_{idx}"

        try:
            handle.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        try:
            with page.expect_download(timeout=15000) as download_info:
                handle.click(timeout=5000, force=True)

            download = download_info.value
            suggested_name = sanitize_filename(download.suggested_filename or f"download_{idx}")
            ext = file_ext_from_name(suggested_name)

            tmp_path_str = download.path()
            size_bytes = 0
            if tmp_path_str:
                tmp_path = Path(tmp_path_str)
                if tmp_path.exists():
                    size_bytes = tmp_path.stat().st_size

            if is_audio_or_video(suggested_name):
                try:
                    download.delete()
                except Exception:
                    pass

                results.append({
                    "file_name": suggested_name,
                    "file_type": simplified_file_type(suggested_name, ""),
                    "status": "skipped_audio_video",
                })
                print(f"  - {label} -> skipped_audio_video")
                continue

            if size_bytes and is_too_large(size_bytes, max_file_size_mb):
                try:
                    download.delete()
                except Exception:
                    pass

                results.append({
                    "file_name": suggested_name,
                    "file_type": simplified_file_type(suggested_name, ""),
                    "status": "skipped_too_large",
                })
                print(f"  - {label} -> skipped_too_large")
                continue

            destination = project_folder / suggested_name
            project_folder.mkdir(parents=True, exist_ok=True)

            if destination.exists() and destination.stat().st_size > 0:
                try:
                    download.delete()
                except Exception:
                    pass

                results.append({
                    "file_name": suggested_name,
                    "file_type": simplified_file_type(suggested_name, ""),
                    "status": "already_downloaded",
                })
                print(f"  - {label} -> already_downloaded")
                continue

            download.save_as(str(destination))

            if destination.exists() and destination.stat().st_size > int(max_file_size_mb * 1024 * 1024):
                destination.unlink(missing_ok=True)
                results.append({
                    "file_name": suggested_name,
                    "file_type": simplified_file_type(suggested_name, ""),
                    "status": "skipped_too_large",
                })
                print(f"  - {label} -> skipped_too_large")
                continue

            results.append({
                "file_name": suggested_name,
                "file_type": simplified_file_type(suggested_name, ""),
                "status": "downloaded",
            })
            print(f"  - {label} -> downloaded")

        except Exception:
            continue

    return results


def ingest_study(context, session: requests.Session, study_url: str, query_string: str, max_file_size_mb: float):
    page = context.new_page()
    metadata = extract_study_metadata(page, study_url, query_string=query_string)

    project_data = {
        "query_string": metadata["query_string"],
        "repository_id": ICPSR_REPOSITORY_ID,
        "repository_url": ICPSR_REPOSITORY_URL,
        "project_url": metadata["project_url"],
        "version": metadata["version"],
        "title": metadata["title"],
        "description": metadata["description"],
        "language": metadata["language"],
        "doi": metadata["doi"],
        "upload_date": metadata["upload_date"],
        "download_date": metadata["download_date"],
        "download_repository_folder": metadata["download_repository_folder"],
        "download_project_folder": metadata["download_project_folder"],
        "download_version_folder": metadata["download_version_folder"],
        "download_method": metadata["download_method"],
    }

    project_id = insert_project(project_data)

    for kw in metadata["keywords"]:
        insert_keyword(project_id, kw)

    for author in metadata["authors"]:
        insert_person_role(project_id, author, "UNKNOWN")

    insert_license(project_id, metadata["license"])

    print(f"\nICPSR study: {metadata['title']}")
    print(f"Study URL: {study_url}")

    if page_is_restricted(page):
        print("  Study is restricted. Saving metadata only and skipping file download.")
        insert_file({
            "project_id": project_id,
            "file_name": "RESTRICTED_STUDY",
            "file_type": "metadata_only",
            "status": "restricted",
        })
        page.close()
        return

    open_data_documentation_tab(page)

    project_folder = ICPSR_DIR / metadata["download_project_folder"]

    # First try real browser-triggered downloads
    download_results = try_playwright_downloads(
        page=page,
        project_folder=project_folder,
        max_file_size_mb=max_file_size_mb,
    )

    if download_results:
        for result in download_results:
            insert_file({
                "project_id": project_id,
                "file_name": result["file_name"],
                "file_type": result["file_type"],
                "status": result["status"],
            })
        page.close()
        return

    # Fallback to direct href download with requests
    links = get_candidate_file_links(page)
    print(f"Candidate links found: {len(links)}")

    if len(links) == 0:
        insert_file({
            "project_id": project_id,
            "file_name": "METADATA_ONLY",
            "file_type": "metadata_only",
            "status": "no_download_links_found",
        })
        page.close()
        return

    seen_results = set()

    for link in links:
        try:
            result = download_file_if_allowed(
                session=session,
                url=link,
                destination_dir=project_folder,
                max_file_size_mb=max_file_size_mb,
            )

            unique_key = (result["file_name"], result["status"])
            if unique_key in seen_results:
                continue
            seen_results.add(unique_key)

            insert_file({
                "project_id": project_id,
                "file_name": result["file_name"],
                "file_type": result["file_type"],
                "status": result["status"],
            })
            print(f"  - {result['file_name']} -> {result['status']}")

        except Exception as e:
            fallback_name = sanitize_filename(Path(urlparse(link).path).name or "unknown_file")
            insert_file({
                "project_id": project_id,
                "file_name": fallback_name,
                "file_type": "unknown",
                "status": f"download_failed: {e}",
            })
            print(f"  - FAILED: {link} -> {e}")

    page.close()


def run_login(headless: bool = False):
    p, context = launch_context(headless=headless)
    try:
        ensure_login(context)
        print("ICPSR login profile saved.")
    finally:
        context.close()
        p.stop()


def run_icpsr(
    limit_studies: int | None = None,
    max_pages_per_query: int = ICPSR_MAX_PAGES_PER_QUERY,
    max_file_size_mb: float = ICPSR_MAX_FILE_SIZE_MB,
    headless: bool = False,
):
    init_db()

    p, context = launch_context(headless=headless)
    try:
        ensure_login(context)
        session = build_requests_session_from_context(context)

        all_urls = set()
        query_map = {}

        try:
            for url in collect_qds_series_results(context):
                all_urls.add(url)
                query_map[url] = "QDS series"
        except Exception as e:
            print(f"QDS series collection failed, continuing without it: {e}")

        for query in ICPSR_SEARCH_TERMS:
            urls = collect_search_results(context, query=query, max_pages=max_pages_per_query)
            for url in urls:
                all_urls.add(url)
                query_map.setdefault(url, query)

        urls = sorted(all_urls)
        if limit_studies is not None:
            urls = urls[:limit_studies]

        print(f"\nTotal ICPSR studies to process: {len(urls)}")

        for i, url in enumerate(urls, start=1):
            print(f"\n[{i}/{len(urls)}] {url}")
            try:
                ingest_study(
                    context=context,
                    session=session,
                    study_url=url,
                    query_string=query_map.get(url, ""),
                    max_file_size_mb=max_file_size_mb,
                )
            except Exception as e:
                print(f"FAILED study {url}: {e}")

        export_all_tables()
        print("\nICPSR run finished. CSV exports updated.")
    finally:
        context.close()
        p.stop()


def main():
    parser = argparse.ArgumentParser(description="ICPSR Playwright acquisition")
    sub = parser.add_subparsers(dest="command", required=True)

    login_parser = sub.add_parser("login", help="Open ICPSR browser profile and save login session")
    login_parser.add_argument("--headless", action="store_true")

    run_parser = sub.add_parser("run", help="Search and ingest ICPSR studies")
    run_parser.add_argument("--limit-studies", type=int, default=None)
    run_parser.add_argument("--max-pages-per-query", type=int, default=ICPSR_MAX_PAGES_PER_QUERY)
    run_parser.add_argument("--max-file-size-mb", type=float, default=ICPSR_MAX_FILE_SIZE_MB)
    run_parser.add_argument("--headless", action="store_true")

    args = parser.parse_args()

    if args.command == "login":
        run_login(headless=args.headless)
    elif args.command == "run":
        run_icpsr(
            limit_studies=args.limit_studies,
            max_pages_per_query=args.max_pages_per_query,
            max_file_size_mb=args.max_file_size_mb,
            headless=args.headless,
        )


if __name__ == "__main__":
    main()