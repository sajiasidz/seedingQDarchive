import re
from pathlib import Path
from urllib.parse import unquote
import requests


def sanitize_filename(name: str) -> str:
    name = unquote(name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:220] if name else "downloaded_file"


def download_file(url: str, destination: Path, session: requests.Session, params: dict = None):
    destination.parent.mkdir(parents=True, exist_ok=True)

    with session.get(url, params=params, stream=True, timeout=180) as response:
        response.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    return destination