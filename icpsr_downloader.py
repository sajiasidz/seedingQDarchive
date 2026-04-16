from database import init_db, export_all_tables
from icpsr_playwright import run_login, run_icpsr

# ==========================================
# ICPSR ONLY
# ==========================================

RUN_ICPSR_LOGIN = False      # set True only if you want to save/refresh login again
RUN_ICPSR = True

ICPSR_LIMIT_STUDIES = None   # None = no limit
ICPSR_MAX_PAGES_PER_QUERY = 10
ICPSR_MAX_FILE_SIZE_MB = 300
ICPSR_HEADLESS = False

RUN_EXPORT_CSV = True

# ==========================================


def main():
    init_db()

    if RUN_ICPSR_LOGIN:
        print("Step 1: Refreshing ICPSR login session...")
        run_login(headless=ICPSR_HEADLESS)

    if RUN_ICPSR:
        print("Step 2: Running ICPSR acquisition...")
        run_icpsr(
            limit_studies=ICPSR_LIMIT_STUDIES,
            max_pages_per_query=ICPSR_MAX_PAGES_PER_QUERY,
            max_file_size_mb=ICPSR_MAX_FILE_SIZE_MB,
            headless=ICPSR_HEADLESS,
        )

    if RUN_EXPORT_CSV:
        print("Step 3: Exporting SQLite tables to CSV...")
        exported = export_all_tables()
        for path in exported:
            print(path)

    print("Done.")


if __name__ == "__main__":
    main()