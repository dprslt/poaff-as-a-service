#!/usr/bin/env python3
"""
POAFF Web Server

A simple Flask web interface to upload a SIA zip file, trigger POAFF
processing, download the resulting archive, and optionally publish a
GitHub release with the airspace output files.
"""

import os
import re
import signal
import shutil
import subprocess
import tempfile
import threading
import uuid
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, abort, jsonify, render_template, request, send_file

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
AUTO_RELEASE = os.environ.get("AUTO_RELEASE", "false").strip().lower() == "true"

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

# Per-job locks so that simultaneous download requests for the same job do
# not race to create the same ZIP archive.
_archive_locks: "dict[str, threading.Lock]" = {}
_archive_locks_lock = threading.Lock()

# The most-recently started job (set before acquiring processing_lock so any
# visitor can observe the queued/running/completed state).
current_job_id: "str | None" = None
current_job_lock = threading.Lock()

JOBS_BASE_DIR = Path("/tmp/poaff_jobs")
JOBS_BASE_DIR.mkdir(parents=True, exist_ok=True)

# Files whose names match this pattern are included in GitHub releases,
# mirroring the pattern from the aip-02-26 release assets.
RELEASE_FILENAME_RE = re.compile(r".+@airspaces-.+\.(txt|geojson)$")

# New SIA delivery zip format: export_xml_bd_sia_YYYY-MM-DD-vXX.zip
# where YYYY-MM-DD is the AIRAC effective date.
ZIP_FILENAME_RE = re.compile(
    r"export_xml_bd_sia_(\d{4})-(\d{2})-(\d{2})-v(\d{2})\.zip$"
)

# Allowed characters for the release prefix
PREFIX_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
PROGRESS_LINE_RE = re.compile(r"^\[[=\s]{1,200}\]\s+\d+\s+%\s+-\s+.+$")
MAX_LOG_LINES = max(int(os.environ.get("POAFF_MAX_LOG_LINES", "2000")), 200)
PROCESS_NICENESS = int(os.environ.get("POAFF_PROCESS_NICENESS", "10"))


class ProcessingStopped(Exception):
    """Raised when a running job is stopped by user request."""


# ---------------------------------------------------------------------------
# AIRAC helpers
# ---------------------------------------------------------------------------

def _parse_airac_from_filename(filename: str) -> Optional[dict]:
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


def _normalize_log_line(line: str) -> str:
    """Strip control sequences and normalize captured process output."""
    clean = ANSI_ESCAPE_RE.sub("", line or "")
    return clean.replace("\r", "").strip()


def _append_job_log(job_id: str, line: str) -> None:
    """Append a stable log line or update the current progress line."""
    clean = _normalize_log_line(line)
    if not clean:
        return

    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return

        if PROGRESS_LINE_RE.match(clean):
            job["progress"] = clean
            return

        job["progress"] = None
        job["logs"].append(clean)

        overflow = len(job["logs"]) - MAX_LOG_LINES
        if overflow > 0:
            del job["logs"][:overflow]
            job["log_start"] += overflow


def _apply_processing_priority(proc: subprocess.Popen) -> None:
    """Reduce the worker process priority so the UI remains responsive."""
    if PROCESS_NICENESS <= 0:
        return

    setpriority = getattr(os, "setpriority", None)
    prio_process = getattr(os, "PRIO_PROCESS", None)
    if setpriority is None or prio_process is None:
        return

    try:
        setpriority(prio_process, proc.pid, PROCESS_NICENESS)
    except OSError:
        return


def _build_job_response(job: dict, since=None, full_snapshot: bool = False) -> dict:
    """Return either a full job snapshot or only log lines after *since*."""
    log_start = job.get("log_start", 0)
    log_count = log_start + len(job["logs"])

    if full_snapshot or since is None or since < log_start or since > log_count:
        logs = list(job["logs"])
        reset_logs = True
    else:
        logs = job["logs"][since - log_start:]
        reset_logs = False

    return {
        "status": job["status"],
        "logs": logs,
        "log_start": log_start,
        "log_count": log_count,
        "progress": job.get("progress"),
        "reset_logs": reset_logs,
        "stop_requested": job.get("stop_requested", False),
        "airac_info": job.get("airac_info"),
        "release_result": job.get("release_result"),
        "prefix": job.get("prefix"),
        "release_configured": job.get("release_config") is not None,
    }


def _stop_requested(job_id: str) -> bool:
    with jobs_lock:
        job = jobs.get(job_id)
        return bool(job and job.get("stop_requested"))


def _set_job_status(job_id: str, status: str) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job["status"] = status


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return

    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (AttributeError, OSError, ProcessLookupError, PermissionError):
        proc.terminate()


def _create_github_release(
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


# ---------------------------------------------------------------------------
# Background processing
# ---------------------------------------------------------------------------

def _run_processing(job_id: str, zip_path: Path, job_dir: Path, prefix: str) -> None:
    """Run the POAFF pipeline in a background thread."""
    global current_job_id  # pylint: disable=global-statement
    # Set current_job_id before acquiring processing_lock so any visitor
    # immediately sees the new job (even while it is queued behind the lock).
    # The /upload route prevents a second job from being accepted while one
    # is already processing, so this assignment is safe in practice.
    with current_job_lock:
        current_job_id = job_id

    try:
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(zip_path, input_dir / zip_path.name)
        _append_job_log(job_id, f"Queued {zip_path.name} for processing ...")

        if _stop_requested(job_id):
            raise ProcessingStopped("Processing stopped before execution started.")

        with processing_lock:
            if _stop_requested(job_id):
                raise ProcessingStopped("Processing stopped before execution started.")

            _append_job_log(job_id, "Processing started.")

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
                bufsize=1,
                env=env,
                start_new_session=True,
            ) as proc:
                _apply_processing_priority(proc)

                with jobs_lock:
                    if job_id in jobs:
                        jobs[job_id]["process"] = proc

                try:
                    if proc.stdout is not None:
                        for line in proc.stdout:
                            _append_job_log(job_id, line)
                    proc.wait()
                finally:
                    with jobs_lock:
                        if job_id in jobs:
                            jobs[job_id]["process"] = None

            if _stop_requested(job_id):
                raise ProcessingStopped("Processing stopped by user.")

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Processing failed (exit code {proc.returncode})"
                )

            # Copy results to the job-specific output directory
            if poaff_output.exists():
                shutil.copytree(poaff_output, output_dir, dirs_exist_ok=True)

        if prefix and prefix != "global":
            _rename_output_files(output_dir, prefix)
            _append_job_log(job_id, f"Output files renamed with prefix '{prefix}'.")

        _append_job_log(job_id, "Processing completed successfully.")
        _set_job_status(job_id, "done")

        # Auto-create GitHub release when configured (from upload form or env vars)
        with jobs_lock:
            job_snapshot = jobs.get(job_id)
            release_config = job_snapshot.get("release_config") if job_snapshot else None
            airac_info = job_snapshot.get("airac_info") if job_snapshot else None

        should_release = (
            release_config is not None
            or (AUTO_RELEASE and GITHUB_TOKEN and GITHUB_REPO)
        )

        if should_release:
            # Gather params: upload form config takes precedence, then env vars, then AIRAC
            gh_token = (release_config["github_token"] if release_config and release_config.get("github_token")
                        else GITHUB_TOKEN)
            gh_repo = (release_config["github_repo"] if release_config and release_config.get("github_repo")
                       else GITHUB_REPO)
            tag = (release_config["tag"] if release_config and release_config.get("tag")
                   else airac_info["tag"] if airac_info
                   else f"aip-{prefix}" if prefix and prefix != "global"
                   else None)
            release_name = (release_config["name"] if release_config and release_config.get("name")
                            else airac_info["name"] if airac_info
                            else tag or "")
            release_body = (release_config["body"] if release_config and release_config.get("body")
                            else airac_info["body"] if airac_info
                            else "")
            is_latest = airac_info["is_latest"] if airac_info else False

            if not gh_token or not gh_repo or not tag:
                _append_job_log(
                    job_id,
                    "WARNING: Auto-release skipped — missing token, repo, or tag."
                )
            else:
                _append_job_log(job_id, f"Auto-creating GitHub release {tag} ...")

                already_exists = False
                check_headers = {
                    "Authorization": f"token {gh_token}",
                    "Accept": "application/vnd.github.v3+json",
                }
                try:
                    check = requests.get(
                        f"https://api.github.com/repos/{gh_repo}/releases/tags/{tag}",
                        headers=check_headers,
                        timeout=15,
                    )
                    if check.status_code == 200:
                        existing = check.json()
                        _append_job_log(
                            job_id,
                            f"WARNING: Tag {tag} already exists at {existing['html_url']}. Skipping."
                        )
                        already_exists = True
                except requests.RequestException as exc:
                    _append_job_log(job_id, f"WARNING: Could not check existing tags: {exc}")

                if not already_exists:
                    result = _create_github_release(
                        release_files=_collect_release_files(output_dir),
                        github_token=gh_token,
                        repo=gh_repo,
                        tag=tag,
                        release_name=release_name,
                        release_body=release_body,
                        is_latest=is_latest,
                    )
                    if "error" in result:
                        _append_job_log(job_id, f"ERROR: Auto-release failed: {result['error']}")
                    else:
                        _append_job_log(
                            job_id,
                            f"✓ Release created: {result['release_url']} "
                            f"({result['uploaded_count']} assets uploaded)"
                        )
                        with jobs_lock:
                            j = jobs.get(job_id)
                            if j:
                                j["release_result"] = result

    except ProcessingStopped as exc:
        _append_job_log(job_id, str(exc))
        _set_job_status(job_id, "stopped")

    except Exception as exc:  # pylint: disable=broad-except
        _append_job_log(job_id, f"ERROR: {exc}")
        _set_job_status(job_id, "error")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    # Reject new uploads while a job is already processing.
    with current_job_lock:
        active_id = current_job_id
    if active_id:
        with jobs_lock:
            active_job = jobs.get(active_id)
        if active_job and active_job["status"] == "processing":
            return jsonify({"error": "A processing job is already running. Please wait for it to finish."}), 409

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

    airac_info = _parse_airac_from_filename(safe_filename)
    if airac_info and not prefix:
        prefix = airac_info["tag"]

    # Optional release config from the upload form
    release_config = None
    if request.form.get("publish_release", "").strip().lower() == "true":
        release_config = {
            "github_token": GITHUB_TOKEN,
            "github_repo": request.form.get("github_repo", "").strip() or GITHUB_REPO,
            "tag": request.form.get("release_tag", "").strip(),
            "name": request.form.get("release_name", "").strip(),
            "body": request.form.get("release_body", "").strip(),
        }
        # Derive tag/name/body from AIRAC if not provided in the form
        if not release_config["tag"] and airac_info:
            release_config["tag"] = airac_info["tag"]
        if not release_config["name"]:
            release_config["name"] = airac_info["name"] if airac_info else release_config["tag"]
        if not release_config["body"]:
            release_config["body"] = airac_info["body"] if airac_info else ""

    with jobs_lock:
        jobs[job_id] = {
            "status": "processing",
            "logs": [],
            "log_start": 0,
            "progress": None,
            "job_dir": job_dir,
            "prefix": prefix or "global",
            "process": None,
            "stop_requested": False,
            "airac_info": airac_info,
            "release_config": release_config,
        }

    thread = threading.Thread(
        target=_run_processing,
        args=(job_id, zip_path, job_dir, prefix or "global"),
        daemon=True,
    )
    thread.start()

    response_data = {"job_id": job_id}
    if airac_info:
        response_data["airac"] = {
            "tag": airac_info["tag"],
            "name": airac_info["name"],
            "body": airac_info["body"],
        }
    return jsonify(response_data)


@app.route("/status/<job_id>")
def status(job_id: str):
    since = request.args.get("since", type=int)
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(_build_job_response(job, since=since))


@app.route("/current")
def current():
    """Return the status of the current (or last) processing job.

    Every visitor can poll this endpoint to observe progress and results
    without needing to know a specific job id.
    """
    with current_job_lock:
        job_id = current_job_id
    if not job_id:
        return jsonify({"job_id": None})
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"job_id": None})
    response = _build_job_response(job, full_snapshot=True)
    response["job_id"] = job_id
    return jsonify(response)


@app.route("/stop/<job_id>", methods=["POST"])
def stop(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404

        if job["status"] != "processing":
            return jsonify({"error": "Only a running job can be stopped."}), 409

        if job.get("stop_requested"):
            return jsonify({"status": "stopping", "stop_requested": True})

        job["stop_requested"] = True
        proc = job.get("process")

    _append_job_log(job_id, "Stop requested by user.")

    if proc is not None:
        _terminate_process(proc)

    return jsonify({"status": "stopping", "stop_requested": True})


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

    # Obtain (or create) a per-job lock so concurrent download requests do not
    # race to build the same archive simultaneously.
    with _archive_locks_lock:
        if job_id not in _archive_locks:
            _archive_locks[job_id] = threading.Lock()
        job_archive_lock = _archive_locks[job_id]

    with job_archive_lock:
        if not archive_path.exists():
            # Collect files from the _POAFF subdirectory only (the SIA/ and
            # log files produced during intermediate parsing steps are not
            # part of the user-facing output).
            poaff_dir = output_dir / "_POAFF"
            search_root = poaff_dir if poaff_dir.exists() else output_dir

            # Write to a temporary file first so that a failed or interrupted
            # archive creation never leaves a corrupt file at archive_path.
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=job_dir, prefix=".tmp_archive_", suffix=".zip"
            )
            try:
                os.close(tmp_fd)
                with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in sorted(search_root.rglob("*")):
                        if p.is_file():
                            # Always compute the archive name relative to
                            # output_dir (not search_root) so that the
                            # _POAFF/ directory prefix is preserved in the
                            # ZIP.  Users extract the archive and navigate
                            # into _POAFF/ to find the airspace files.
                            zf.write(p, p.relative_to(output_dir))
                os.replace(tmp_path, archive_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

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

    data = request.get_json(force=True, silent=True) or {}

    github_token = GITHUB_TOKEN
    repo = data.get("repo", "") or GITHUB_REPO

    if not github_token or not repo:
        return jsonify({"error": "GitHub token and repo are required (set via env vars or request body)."}), 400

    if not re.match(r"^[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+$", repo):
        return jsonify({"error": "Invalid repository format. Use 'owner/repo'."}), 400

    # Derive tag/name/body from AIRAC info when available
    airac_info = job.get("airac_info")
    tag = data.get("tag", "").strip()
    if not tag and airac_info:
        tag = airac_info["tag"]
    elif not tag:
        prefix = job.get("prefix", "")
        tag = f"aip-{prefix}" if prefix and prefix != "global" else ""

    release_name = data.get("name", "").strip() or (airac_info["name"] if airac_info else tag)
    release_body = data.get("body", "").strip() or (airac_info["body"] if airac_info else "")
    is_latest = airac_info["is_latest"] if airac_info else False

    if not tag:
        return jsonify({"error": "Tag name is required (set via request body or derive from filename)."}), 400

    output_dir = job["job_dir"] / "output"
    release_files = _collect_release_files(output_dir)
    if not release_files:
        return jsonify({"error": "No release files found matching the airspace pattern."}), 400

    result = _create_github_release(
        release_files=release_files,
        github_token=github_token,
        repo=repo,
        tag=tag,
        release_name=release_name,
        release_body=release_body,
        is_latest=is_latest,
    )

    if "error" in result:
        return jsonify({"error": result["error"]}), 400

    with jobs_lock:
        j = jobs.get(job_id)
        if j:
            j["release_result"] = result

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
