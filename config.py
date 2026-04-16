from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DOWNLOAD_DIR = BASE_DIR / "downloads"
DB_DIR = BASE_DIR / "db"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"

DB_PATH = DB_DIR / "metadata.db"

DANS_DIR = DOWNLOAD_DIR / "dans"
ICPSR_DIR = DOWNLOAD_DIR / "icpsr_private"

DANS_REPOSITORY_ID = 5
ICPSR_REPOSITORY_ID = 15

DANS_BASE_URL = "https://ssh.datastations.nl"
DANS_REPOSITORY_URL = f"{DANS_BASE_URL}/dataverse/root"

# ICPSR
ICPSR_BASE_URL = "https://www.icpsr.umich.edu"
ICPSR_REPOSITORY_URL = "https://www.icpsr.umich.edu/web/ICPSR/search/studies"
ICPSR_SERIES_URL = "https://www.icpsr.umich.edu/web/ICPSR/series/1780"

# Playwright profile folder for saved ICPSR login
ICPSR_PROFILE_DIR = BASE_DIR / ".playwright" / "icpsr_profile"

# General settings
REQUEST_TIMEOUT = 90
USER_AGENT = "qdarchive-part1/0.1 (student project; local use only)"

# File extensions
QDA_EXTENSIONS = {
    ".qdpx", ".qdc", ".mqda", ".nvp", ".nvpx", ".atlasproj",
    ".hpr7", ".ppj", ".pprj", ".qlt", ".f4p", ".qpd"
}

PRIMARY_DATA_EXTENSIONS = {
    ".txt", ".pdf", ".rtf", ".doc", ".docx", ".odt",
    ".md", ".html", ".htm", ".csv", ".tsv",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff"
}

# Exclude audio/video
EXCLUDED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".avi", ".mov", ".mkv", ".wmv", ".webm", ".mpeg", ".mpg"
}

# Size limits
MAX_FILE_SIZE_MB = 300
ICPSR_MAX_FILE_SIZE_MB = 300

# DANS search terms
DANS_FILE_SEARCH_TERMS = [
    "qdpx", "qdc", "mqda", "nvp", "nvpx", "atlasproj", "f4p"
]

DANS_DATASET_SEARCH_TERMS = [
    "qualitative research",
    "qualitative interview",
    "interview transcript",
    "qualitative analysis",
]

# ICPSR search terms
ICPSR_SEARCH_TERMS = [
    '"qualitative interview"',
    '"interview transcript"',
    '"qualitative data"',
    '"in-depth interview"',
    '"ethnographic interview"'
]

ICPSR_MAX_PAGES_PER_QUERY = 10

# Create folders automatically
for folder in [
    DOWNLOAD_DIR,
    DB_DIR,
    EXPORT_DIR,
    LOG_DIR,
    DANS_DIR,
    ICPSR_DIR,
    ICPSR_PROFILE_DIR,
]:
    folder.mkdir(parents=True, exist_ok=True)