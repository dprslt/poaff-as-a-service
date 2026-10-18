#!/usr/bin/env python3
"""
Headless POAFF run: download a SIA zip, process it, publish the GitHub release.

Same pipeline as an upload on the web server with "publish release" ticked,
without the browser. Used by .github/workflows/sia-release.yml, which runs it
inside the dprslt/poaff-web image (it needs /app/docker-entrypoint.py and the
POAFF paths under /app/poaff_bpa).

    GITHUB_TOKEN=... GITHUB_REPO=owner/repo \\
        python webserver/publish_cli.py --zip-url <SIA download link>
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from poaff_release import (
    collect_release_files,
    create_github_release,
    find_release,
    parse_airac_from_filename,
    rename_output_files,
)

ENTRYPOINT = "/app/docker-entrypoint.py"
POAFF_OUTPUT = Path("/app/poaff_bpa/output")
CONTENT_DISPOSITION_RE = re.compile(r'filename="?([^";]+)"?')


def download_zip(url: str, dest_dir: Path) -> Path:
    """Download *url* into *dest_dir*, keeping the server-provided file name.

    The SIA links end in an opaque id; the AIRAC date is only in the
    Content-Disposition name (export_xml_bd_sia_YYYY-MM-DD-vXX.zip).
    """
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        match = CONTENT_DISPOSITION_RE.search(resp.headers.get("Content-Disposition", ""))
        if not match:
            sys.exit(f"ERROR: no file name in Content-Disposition for {url}")
        path = dest_dir / Path(match.group(1)).name
        with open(path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    print(f"Downloaded {path.name} ({path.stat().st_size} bytes)")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--zip-url", help="SIA download link")
    source.add_argument("--zip-file", type=Path, help="Local SIA zip")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()
    if not token or not repo:
        sys.exit("ERROR: GITHUB_TOKEN and GITHUB_REPO are required")

    work_dir = Path(tempfile.mkdtemp(prefix="poaff_cli_"))
    input_dir = work_dir / "input"
    input_dir.mkdir()
    if args.zip_url:
        zip_path = download_zip(args.zip_url, input_dir)
    else:
        zip_path = input_dir / args.zip_file.name
        shutil.copy2(args.zip_file, zip_path)

    airac_info = parse_airac_from_filename(zip_path.name)
    if not airac_info:
        sys.exit(f"ERROR: {zip_path.name} does not look like export_xml_bd_sia_YYYY-MM-DD-vXX.zip")
    tag = airac_info["tag"]

    # Check before the long processing run, not after.
    existing = find_release(repo, tag, token)
    if existing:
        print(f"Release {tag} already exists at {existing['html_url']}. Nothing to do.")
        return

    print(f"Processing {zip_path.name} for release {tag} ...", flush=True)
    if POAFF_OUTPUT.exists():
        shutil.rmtree(POAFF_OUTPUT)
    subprocess.run(
        [sys.executable, ENTRYPOINT],
        env={**os.environ, "PYTHONUNBUFFERED": "1", "POAFF_INPUT_DIR": str(input_dir)},
        check=True,
    )

    rename_output_files(POAFF_OUTPUT, tag)
    release_files = collect_release_files(POAFF_OUTPUT)
    if not release_files:
        sys.exit("ERROR: processing produced no release files")

    result = create_github_release(
        release_files=release_files,
        github_token=token,
        repo=repo,
        tag=tag,
        release_name=airac_info["name"],
        release_body=airac_info["body"],
        is_latest=airac_info["is_latest"],
    )
    if "error" in result:
        sys.exit(f"ERROR: {result['error']}")
    print(f"Release created: {result['release_url']} ({result['uploaded_count']} assets uploaded)")
    if result["failed_count"]:
        sys.exit(f"ERROR: {result['failed_count']} assets failed to upload: {result['failed']}")


if __name__ == "__main__":
    main()
