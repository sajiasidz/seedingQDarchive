from config import EXPORT_DIR
from database import init_db, export_all_tables
from dans_api import collect_dans_candidates, ingest_from_csv

# --------------------------------------------------
# DANS FIRST
# --------------------------------------------------

RUN_DANS_SEARCH = True
RUN_DANS_INGEST = True

# page size per API request
DANS_MAX_RESULTS_PER_QUERY = 100

# None = ingest all rows from the CSV
DANS_INGEST_LIMIT = None

DANS_DOWNLOAD_FILES = True
DANS_MAX_FILE_SIZE_MB = 300


# EXPORT
RUN_EXPORT_CSV = True

# --------------------------------------------------


def main():
    init_db()

    if RUN_DANS_SEARCH:
        print("Step 1: Searching DANS...")
        collect_dans_candidates(per_page=DANS_MAX_RESULTS_PER_QUERY)

    if RUN_DANS_INGEST:
        print("Step 2: Downloading and storing DANS datasets...")
        ingest_from_csv(
            csv_path=str(EXPORT_DIR / "dans_candidates.csv"),
            limit=DANS_INGEST_LIMIT,
            download_files=DANS_DOWNLOAD_FILES,
            max_file_size_mb=DANS_MAX_FILE_SIZE_MB,
        )

    if RUN_EXPORT_CSV:
        print("Step 5: Exporting SQLite tables to CSV...")
        exported = export_all_tables()
        for path in exported:
            print(path)

    print("Done.")


if __name__ == "__main__":
    main()