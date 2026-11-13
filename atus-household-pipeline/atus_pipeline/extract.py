"""Extract: download (with caching) and read the BLS ATUS zip files."""
from __future__ import annotations

import hashlib
import logging
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from . import config

log = logging.getLogger(__name__)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(filename: str, raw_dir: Path, refresh: bool = False) -> Path:
    """Download one BLS file into raw_dir, reusing a cached copy if present."""
    dest = raw_dir / filename
    if dest.exists() and not refresh:
        log.info("Using cached %s", dest)
        return dest
    raw_dir.mkdir(parents=True, exist_ok=True)
    url = f"{config.BLS_BASE_URL}/{filename}"
    log.info("Downloading %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)
    tmp.rename(dest)  # atomic: never leave a half-downloaded file in the cache
    return dest


def read_zipped_csv(zip_path: Path, usecols: list[str]) -> pd.DataFrame:
    """Read the single CSV-format data file (.dat/.csv) inside a BLS zip.

    TUCASEID is read as a string: it is a 14-digit identifier, not a number,
    and keeping it as text avoids any float/precision surprises.
    """
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith((".dat", ".csv"))]
        if len(members) != 1:
            raise ValueError(f"{zip_path.name}: expected 1 data file, found {members}")
        with zf.open(members[0]) as f:
            df = pd.read_csv(f, usecols=usecols, dtype={"TUCASEID": "string"})
    log.info("Read %s: %d rows", zip_path.name, len(df))
    return df[usecols]
