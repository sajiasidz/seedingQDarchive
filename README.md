# QDArchive Seeding Project
**Student:** Rabeya Siddika Sajia                                                                                                                                   
**Student ID:** 23084716  
**GitHub:** sajiasidz                                                                                                                             
**University:** FAU Erlangen-Nürnberg  
**Supervisor:** Prof. Dr. Dirk Riehle  
**Course:** Seeding QDArchive / Data Science Project (10 ECTS)  

## Overview

This project supports the seeding of QDArchive by collecting metadata and files from qualitative data repositories and then classifying the collected projects. The work is divided into two parts:

- **Part 1: Data acquisition** from DANS and ICPSR
- **Part 2: Project type filtering and ISIC Rev. 5 classification**

The assigned repositories are:

| Repository | repository_id | URL |
|---|---:|---|
| DANS | 5 | https://dans.knaw.nl/en/ |
| ICPSR | 15 | https://icpsr.umich.edu |

## Repository Structure

```
.
├── config.py                                       # global settings, paths, repository IDs, search terms, limits
├── dans_api.py                                     # DANS search, metadata extraction, and file download logic
├── dans_downloader.py                              # runner script for the DANS acquisition workflow
├── database.py                                     # SQLite schema, insert functions, and CSV export
├── downloader.py                                   # shared helper functions for downloading files and cleaning file names
├── icpsr_downloader.py                             # runner script for the ICPSR acquisition workflow
├── icpsr_playwright.py                             # ICPSR search, login handling, metadata collection, and download automation
├── class_1_project_type.py                         # assigns project types based on file extensions          
├── class_2_import_isic.py                          # imports ISIC Rev. 5 sections and divisions into the database
├── class_3_prepare_targets.py                      # prepares project-level and file-level inputs for classification
├── class_4_run_isic_classifier.py                  # runs the TF-IDF ISIC classifier and stores classification results
├── class_5_create_submission_xlsx.py               # creates the final XLSX submission table
├── class_6_create_final_db.py                      # creates the final SQLite database copy for submission
├── class_7_create_pdf_report.py                    # generates the final PDF report with statistics, analysis, and comments
├── downloads/                                      # downloaded repository files
│   ├── dans/                                       # downloaded files from DANS
│   └── icpsr_private/                              # downloaded files from ICPSR (private/internal use)
├── db/                                             # SQLite metadata database
    ├── 23084716-sq26-classification.db             # SQLite metadata database (submission file)
    └── metadata.db                                 # Working copy of the database
├── exports/
    ├── 23084716-sq26-classification-table.xlsx     # final XLSX table required for submission
    └── 23084716-sq26-classification-report.pdf     # final PDF report with methodology and results
                                  


```

---

## Database Schema

The original acquisition database contains these core tables:

| Table | Description |
|---|---|
| `projects` | One row per downloaded project/dataset |
| `files` | One row per file within a project |
| `keywords` | Keywords associated with each project |
| `person_role` | Authors/contributors and their roles |
| `licenses` | License information per project |

Part 2 adds these tables/fields:

| Table / Field | Purpose |
|---|---|
| `projects.project_type` | QDA_PROJECT, QD_PROJECT, OTHER_PROJECT, or NOT_A_PROJECT |
| `isic_sections` | ISIC Rev. 5 section-level taxonomy |
| `isic_divisions` | ISIC Rev. 5 division-level taxonomy |
| `classification_targets` | Project-level and file-level inputs for classification |
| `classification_results` | Primary and secondary ISIC classification results |

## Part 1: Data Acquisition

### DANS

DANS is accessed through the Dataverse API. The pipeline searches for qualitative data candidates, collects project metadata, downloads eligible files, and stores all results in the SQLite database.

### ICPSR

ICPSR is accessed with Playwright because the website is JavaScript-based and may require login. The pipeline saves a browser session, collects likely qualitative studies, and stores metadata. In this run, ICPSR files were restricted or login-required, so the database contains metadata-only records for ICPSR.

## Part 2: Classification Workflow

The classification workflow is implemented in separate step scripts:

| Step | Script | Output |
|---|---|---|
| 1 | `classification_step1_project_type.py` | Adds `project_type` to `projects` |
| 2 | `classification_step2_import_isic.py` | Imports ISIC sections and divisions |
| 3 | `classification_step3_prepare_targets.py` | Creates project/file classification targets |
| 4 | `classification_step4_run_isic_classifier.py` | Runs TF-IDF ISIC classifier |
| 5 | `classification_step5_create_submission_xlsx.py` | Creates final XLSX table |
| 6 | `classification_step6_create_final_db_copy.py` | Creates final database copy |
| 7 | `classification_step7_create_report_statistics.py` | Creates report statistics and SVG charts |
| 8 | `classification_step8_create_pdf_report.py` | Creates final PDF report |

The classifier uses **ISIC Rev. 5 division-level classes**. It classifies only `QDA_PROJECT` and `QD_PROJECT` entries, including both project-level targets and primary-data-file targets.

## Results Summary

### Project counts by repository

| Repository | Projects |
|---|---:|
| DANS | 5804 |
| ICPSR | 132 |
| **Total** | **5936** |

### Project type distribution

| Repository | Project type | Count |
|---|---|---:|
| DANS | QDA_PROJECT | 7 |
| DANS | QD_PROJECT | 4570 |
| DANS | OTHER_PROJECT | 1220 |
| DANS | NOT_A_PROJECT | 7 |
| ICPSR | NOT_A_PROJECT | 132 |

### Classification results

| Target level | Count |
|---|---:|
| Project-level targets | 4577 |
| File-level primary data targets | 63932 |
| **Total classification results** | **68509** |

ICPSR is included in the final XLSX table, but its ISIC class fields are empty because all ICPSR projects were classified as `NOT_A_PROJECT`. This happened because the available ICPSR records were metadata-only, restricted, or login-required and did not provide usable file extensions for project-type detection.

## Final Submission Files

The main final outputs are:

```text
db/23084716-sq26-classification.db
exports/23084716-sq26-classification-table.xlsx
exports/23084716-sq26-classification-report.pdf
```

The XLSX table contains:

```text
repository_id
project_type
project_title
primary_class
secondary_class
no_project_files
```

`OTHER_PROJECT` and `NOT_A_PROJECT` rows are included for completeness, but their ISIC classification fields are intentionally empty.

## How to Run

Install dependencies:

```bash
pip install pandas requests playwright openpyxl scikit-learn matplotlib reportlab
playwright install
```

Run acquisition if needed:

```bash
python dans_downloader.py
python icpsr_playwright.py login
python icpsr_downloader.py
```

Run Part 2 classification workflow:

```bash
python class_1_project_type.py
python class_2_import_isic.py
python class_3_prepare_targets.py
python class_4_run_isic_classifier.py
python class_5_create_submission_xlsx.py
python class_6_create_final_db_copy.py
python class_7_create_pdf_report.py
```

## Notes

- The classification is an automatic first-pass classification, not manually validated.
- TF-IDF similarity was used because it is simple, reproducible, and transparent.
- Low-confidence or unexpected classes can occur when project metadata is short or generic.
- The repository should be tagged as `classification-results` for the final Part 2 submission.
