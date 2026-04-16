# QDArchive Seeding Project

**Student:** Rabeya Siddika Sajia 

**Student ID:** 23084716

**GitHub:** sajiasidz

**University:** FAU Erlangen-Nürnberg 

**Supervisor:** Prof. Dr. Dirk Riehle  
**Course:** Data Science Project (10 ECTS)  
**Deadline:** April 17, 2026

## Overview

This project seeds the [QDArchive](https://qdarchive.org) repository by harvesting qualitative data analysis (QDA) files and metadata from assigned data repositories. The goal is to collect datasets that contain QDA project files (e.g. NVivo, ATLAS.ti, MAXQDA) and store their metadata in a structured SQLite database.


**Assigned repositories:**
- **DANS** (`repository_id = 5`) — https://dans.knaw.nl/en/
- **ICPSR** (`repository_id = 15`) — https://icpsr.umich.edu

## Repository Structure

```
.
├── config.py              # global settings, paths, repository IDs, search terms, limits
├── dans_api.py            # DANS search, metadata extraction, and file download logic
├── dans_downloader.py     # runner script for the DANS acquisition workflow
├── database.py            # SQLite schema, insert functions, and CSV export
├── downloader.py          # shared helper functions for downloading files and cleaning file names
├── icpsr_downloader.py    # runner script for the ICPSR acquisition workflow
├── icpsr_playwright.py    # ICPSR search, login handling, metadata collection, and download automation
├── downloads/             # downloaded repository files
│   ├── dans/              # downloaded files from DANS
│   └── icpsr_private/     # downloaded files from ICPSR (private/internal use)
├── db/                    # SQLite metadata database
    ├── 23084716-sq26.db   # SQLite metadata database (submission file)
    ├── metadata.db        # Working copy of the database


```

---

## Database Schema

The metadata is stored in a 5-table SQLite database following the QDArchive schema:

| Table | Description |
|---|---|
| `projects` | One row per downloaded project/dataset |
| `files` | One row per file within a project |
| `keywords` | Keywords associated with each project |
| `person_role` | Authors/contributors and their roles |
| `licenses` | License information per project |

### File Download Status Values
- `SUCCEEDED` — File downloaded successfully
- `RESTRICTED` — Restricted access, only metadata taken
- `FAILED_LOGIN_REQUIRED` — File requires authentication
- `FAILED_SERVER_UNRESPONSIVE` — Server error or rate limit
- `FAILED_TOO_LARGE` — File skipped (audio/video or >200MB)

---

## Results Summary

| Repository | Projects | Files Downloaded |
|---|---|---|
| DANS | 5804 | 53707 |
| ICPSR | 132 | 0 |
| **Total** | **5936** | **53707** |

---

## How to Run

### Install dependencies:
```bash
pip install pandas requests playwright
playwright install
```

### Run DANS acquisition
```bash
python dans_downloader.py
```

### Save ICPSR login session
```bash
python icpsr_playwright.py login
```

### Run ICPSR acquisition
```bash
python icpsr_downloader.py
```

---

## Downloader Details

### DANS (Data Archiving and Networked Services)
- Uses the Dataverse API to search DANS datasets and collect candidate project IDs.
- Extracts project metadata such as title, description, language, keywords, authors, version, and license information before downloading files.
- Downloads files individually using the DANS file access endpoint instead of downloading one large bundle.
- Excludes audio and video files based on file extension or content type and also files larger than 300 MB.
- Stores both project metadata and file status in the SQLite database during ingestion.

### ICPSR (Inter-university Consortium for Political and Social Research)
- Uses Playwright because ICPSR is JavaScript-driven and requires browser interaction for searching and downloading.
- Reuses a persistent browser profile so the login session can be saved and reused across runs.
- Filters study pages to keep likely qualitative studies and skips pages that return service unavailable errors.
- Detects restricted studies and stores them as metadata only without downloading files.
- Saves file statuses such as downloaded, restricted, no_download_links_found, skipped_audio_video, and skipped_too_large in the database.


