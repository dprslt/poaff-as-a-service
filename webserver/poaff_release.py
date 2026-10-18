"""
Release helpers shared by the web server (app.py) and the headless CLI
(publish_cli.py): AIRAC cycle from the SIA zip name, output renaming, and
GitHub release creation.
"""

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests

# Files whose names match this pattern are included in GitHub releases,
# mirroring the pattern from the aip-02-26 release assets.
RELEASE_FILENAME_RE = re.compile(r".+@airspaces-.+\.(txt|geojson)$")

# New SIA delivery zip format: export_xml_bd_sia_YYYY-MM-DD-vXX.zip
# where YYYY-MM-DD is the AIRAC effective date.
ZIP_FILENAME_RE = re.compile(
    r"export_xml_bd_sia_(\d{4})-(\d{2})-(\d{2})-v(\d{2})\.zip$"
)


# ---------------------------------------------------------------------------
# AIRAC helpers
# ---------------------------------------------------------------------------

def parse_airac_from_filename(filename: str) -> Optional[dict]:
    """Extract AIRAC cycle info from a SIA delivery zip filename.

    Expected filename format:
        export_xml_bd_sia_YYYY-MM-DD-vXX.zip

    Returns a dict with tag, name, body, dates, cycle number, etc., or None
    if the filename does not match.
    """
    m = ZIP_FILENAME_RE.match(filename)
    if not m:
        return None

    year, month, day, _version = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    start_date = date(year, month, day)
    end_date = start_date + timedelta(days=27)

    # AIRAC cycles: 28-day cycles from epoch 1901-01-10
    epoch = date(1901, 1, 10)
    jan1 = date(year, 1, 1)
    days_since_epoch = (jan1 - epoch).days
    offset = days_since_epoch % 28
    first_of_year = jan1 if offset == 0 else jan1 + timedelta(days=28 - offset)
    delta_in_year = (start_date - first_of_year).days
    cycle = (delta_in_year // 28) + 1
    year_short = year % 100

    tag = f"aip-{cycle:02d}-{year_short:02d}"
    name = f"AIP {cycle:02d}/{year_short:02d}"
    body = (
        f"En vigueur du {start_date.strftime('%d/%m/%Y')} "
        f"au {end_date.strftime('%d/%m/%Y')} inclus"
    )

    # Mark as latest if this cycle has not yet fully ended
    is_latest = end_date >= date.today()

    return {
        "tag": tag,
        "name": name,
        "body": body,
        "start_date": start_date,
        "end_date": end_date,
        "cycle": cycle,
        "year_short": year_short,
        "is_latest": is_latest,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def collect_release_files(output_dir: Path) -> list:
    """Return paths of files that should be uploaded to a GitHub release."""
    results = []
    poaff_dir = output_dir / "_POAFF"
    search_root = poaff_dir if poaff_dir.exists() else output_dir
    for p in sorted(search_root.rglob("*")):
        if p.is_file() and RELEASE_FILENAME_RE.match(p.name):
            results.append(p)
    return results


def rename_output_files(output_dir: Path, prefix: str) -> None:
    """Replace the 'global@' prefix with *prefix*@ in every output file."""
    poaff_dir = output_dir / "_POAFF"
    search_root = poaff_dir if poaff_dir.exists() else output_dir
    for p in list(search_root.rglob("*")):
        if p.is_file() and p.name.startswith("global@"):
            p.rename(p.parent / p.name.replace("global@", f"{prefix}@", 1))


def create_github_release(
    release_files: list,
    github_token: str,
    repo: str,
    tag: str,
    release_name: str,
    release_body: str,
    is_latest: bool = False,
) -> dict:
    """Create a GitHub release and upload airspace assets.

    Returns a dict with 'release_url', 'uploaded', and 'failed' keys.
    """
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    payload = {
        "tag_name": tag,
        "name": release_name,
        "body": release_body,
    }
    if is_latest:
        payload["make_latest"] = "true"
    else:
        payload["make_latest"] = "false"

    resp = requests.post(
        f"https://api.github.com/repos/{repo}/releases",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return {"error": f"GitHub API error: {resp.text}"}

    release_info = resp.json()
    upload_url_base = (
        f"https://uploads.github.com/repos/{repo}/releases/{release_info['id']}/assets"
    )

    uploaded = []
    failed = []

    for file_path in release_files:
        content_type = {
            ".geojson": "application/geo+json",
            ".txt": "text/plain",
            ".kml": "application/vnd.google-earth.kml+xml",
        }.get(file_path.suffix.lower(), "application/octet-stream")

        try:
            with open(file_path, "rb") as fh:
                up = requests.post(
                    f"{upload_url_base}?name={file_path.name}",
                    data=fh.read(),
                    headers={**headers, "Content-Type": content_type},
                    timeout=120,
                )
            if up.status_code in (200, 201):
                uploaded.append(file_path.name)
            else:
                failed.append({"file": file_path.name, "error": up.text})
        except Exception as exc:  # pylint: disable=broad-except
            failed.append({"file": file_path.name, "error": str(exc)})

    return {
        "release_url": release_info["html_url"],
        "uploaded_count": len(uploaded),
        "failed_count": len(failed),
        "uploaded": uploaded,
        "failed": failed,
    }


def find_release(repo: str, tag: str, github_token: str) -> Optional[dict]:
    """Return the GitHub release for *tag*, or None when it does not exist."""
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        headers={
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=15,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()
