#!/usr/bin/env python3
"""
POAFF Web Server

A simple Flask web interface to upload a SIA zip file, trigger POAFF
processing, download the resulting archive, and optionally publish a
GitHub release with the airspace output files.
"""

import os
import re
import shutil
import subprocess
import threading
import uuid
import zipfile
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, render_template, request, send_file

app = Flask(__name__)

# ---------------------------------------------------------------------------
# In-memory job store
# jobs[job_id] = {
#   'status':  'processing' | 'done' | 'error',
#   'logs':    [str, ...],
#   'job_dir': Path,
#   'prefix':  str,
# }
# ---------------------------------------------------------------------------
jobs: dict = {}
jobs_lock = threading.Lock()

# A lock so only one POAFF processing run executes at a time (the tool uses
# fixed /app paths for AIXM input data during execution).
processing_lock = threading.Lock()

JOBS_BASE_DIR = Path("/tmp/poaff_jobs")
JOBS_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Files whose names match this pattern are included in GitHub releases,
# mirroring the pattern from the aip-02-26 release assets.
RELEASE_FILENAME_RE = re.compile(r".+@airspaces-.+\.(txt|geojson)$")

# Allowed characters for the release prefix
PREFIX_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_release_files(output_dir: Path) -> list:
    """Return paths of files that should be uploaded to a GitHub release."""
    results = []
    poaff_dir = output_dir / "_POAFF"
    search_root = poaff_dir if poaff_dir.exists() else output_dir
    for p in sorted(search_root.rglob("*")):
        if p.is_file() and RELEASE_FILENAME_RE.match(p.name):
            results.append(p)
    return results


def _rename_output_files(output_dir: Path, prefix: str) -> None:
    """Replace the 'global@' prefix with *prefix*@ in every output file."""
    poaff_dir = output_dir / "_POAFF"
    search_root = poaff_dir if poaff_dir.exists() else output_dir
    for p in list(search_root.rglob("*")):
        if p.is_file() and p.name.startswith("global@"):
            p.rename(p.parent / p.name.replace("global@", f"{prefix}@", 1))


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def _run_processing(job_id: str, zip_path: Path, job_dir: Path, prefix: str) -> None:
    """Run the POAFF pipeline in a background thread."""
    logs = jobs[job_id]["logs"]

    try:
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(zip_path, input_dir / zip_path.name)
        logs.append(f"Queued {zip_path.name} for processing …")

        with processing_lock:
            logs.append("Processing started.")

            # Clean previous run's artefacts from the shared POAFF paths so
            # the tool starts from a clean state.
            sia_input = Path("/app/poaff_bpa/input/SIA")
            poaff_output = Path("/app/poaff_bpa/output")
            if sia_input.exists():
                shutil.rmtree(sia_input)
            if poaff_output.exists():
                shutil.rmtree(poaff_output)

            env = {**os.environ, "PYTHONUNBUFFERED": "1",
                   "POAFF_INPUT_DIR": str(input_dir)}

            with subprocess.Popen(
                ["python", "/app/docker-entrypoint.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            ) as proc:
                for line in proc.stdout:
                    logs.append(line.rstrip())
                proc.wait()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Processing failed (exit code {proc.returncode})"
                )

            # Copy results to the job-specific output directory
            if poaff_output.exists():
                shutil.copytree(poaff_output, output_dir, dirs_exist_ok=True)

        if prefix and prefix != "global":
            _rename_output_files(output_dir, prefix)
            logs.append(f"Output files renamed with prefix '{prefix}'.")

        logs.append("Processing completed successfully.")
        with jobs_lock:
            jobs[job_id]["status"] = "done"

    except Exception as exc:  # pylint: disable=broad-except
        logs.append(f"ERROR: {exc}")
        with jobs_lock:
            jobs[job_id]["status"] = "error"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400
    if not file.filename.lower().endswith(".zip"):
        return jsonify({"error": "Only .zip files are accepted."}), 400

    prefix = request.form.get("prefix", "").strip()
    if prefix and not PREFIX_RE.match(prefix):
        return jsonify({
            "error": "Invalid prefix. Use only letters, digits, hyphens or underscores."
        }), 400

    job_id = str(uuid.uuid4())
    job_dir = JOBS_BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = Path(file.filename).name
    zip_path = job_dir / safe_filename
    file.save(zip_path)

    with jobs_lock:
        jobs[job_id] = {
            "status": "processing",
            "logs": [],
            "job_dir": job_dir,
            "prefix": prefix or "global",
        }

    thread = threading.Thread(
        target=_run_processing,
        args=(job_id, zip_path, job_dir, prefix or "global"),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/status/<job_id>")
def status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify({"status": job["status"], "logs": job["logs"]})


@app.route("/download/<job_id>")
def download(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        abort(404)
    if job["status"] != "done":
        abort(400)

    prefix = job["prefix"]
    job_dir = job["job_dir"]
    output_dir = job_dir / "output"
    archive_path = job_dir / f"{prefix}_results.zip"

    if not archive_path.exists():
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if output_dir.exists():
                for p in output_dir.rglob("*"):
                    if p.is_file():
                        zf.write(p, p.relative_to(output_dir))

    return send_file(
        archive_path,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{prefix}_results.zip",
    )


@app.route("/release/<job_id>", methods=["POST"])
def create_release(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Job not found or not yet completed."}), 400

    data = request.get_json(silent=True) or {}
    github_token = data.get("token", "").strip()
    repo = data.get("repo", "").strip()   # "owner/repo"
    tag = data.get("tag", "").strip()
    release_name = data.get("name", tag).strip()
    release_body = data.get("body", "").strip()

    if not github_token or not repo or not tag:
        return jsonify({"error": "Fields 'token', 'repo', and 'tag' are required."}), 400

    if not re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+$", repo):
        return jsonify({"error": "Invalid repository format. Use 'owner/repo'."}), 400

    output_dir = job["job_dir"] / "output"
    release_files = _collect_release_files(output_dir)
    if not release_files:
        return jsonify({"error": "No release files found matching the airspace pattern."}), 400

    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Create the release
    resp = requests.post(
        f"https://api.github.com/repos/{repo}/releases",
        json={"tag_name": tag, "name": release_name, "body": release_body},
        headers=headers,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return jsonify({"error": f"GitHub API error: {resp.text}"}), 400

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

    return jsonify({
        "release_url": release_info["html_url"],
        "uploaded_count": len(uploaded),
        "failed_count": len(failed),
        "uploaded": uploaded,
        "failed": failed,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
