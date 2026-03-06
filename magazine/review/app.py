"""Unified Flask web app for import, review, story setup, and PDF generation."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash

from magazine.config import (
    FACE_RESULTS,
    TARGET_FACE_COUNT,
    THUMBNAILS_DIR,
    ORIGINALS_DIR,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
)
from magazine.layout.engine import estimate_page_count
from magazine.services.importer import import_uploaded_files, import_existing_paths
from magazine.services.state import (
    load_json,
    load_photos_manifest,
    load_review_state,
    save_review_state,
    normalize_review_entry,
    load_story_config,
    save_story_config,
)
from magazine.sources.google_picker import GooglePhotoPicker


_GOOGLE_JOBS: dict[str, dict] = {}
_GOOGLE_JOBS_LOCK = threading.Lock()
_JOB_BATCH_SIZE = 2
_JOB_DIR = Path(THUMBNAILS_DIR).parent / "import_jobs"
_JOB_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)


def _job_path(job_id: str) -> Path:
    return _JOB_DIR / f"{job_id}.json"


def _sanitize_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "picker"}


def _write_job_file(job_id: str, job: dict):
    _job_path(job_id).write_text(json.dumps(_sanitize_job(job), indent=2))


def _record_job_event(job_id: str, stage: str, message: str, **details):
    timestamp = datetime.now(timezone.utc).isoformat()
    with _GOOGLE_JOBS_LOCK:
        job = _GOOGLE_JOBS.get(job_id, {})
        events = list(job.get("events", []))
        events.append(
            {
                "time": timestamp,
                "stage": stage,
                "message": message,
                "details": details,
            }
        )
        job["events"] = events[-40:]
        _GOOGLE_JOBS[job_id] = job
        try:
            _write_job_file(job_id, job)
        except Exception:
            logger.exception("Failed writing job file", extra={"job_id": job_id})
    logger.info("google_job stage=%s job_id=%s message=%s details=%s", stage, job_id, message, details)


def _face_count(value) -> int:
    if isinstance(value, dict):
        return int(value.get("face_count", -1))
    try:
        return int(value)
    except Exception:
        return -1


def _set_job(job_id: str, **changes):
    with _GOOGLE_JOBS_LOCK:
        job = _GOOGLE_JOBS.get(job_id, {})
        job.update(changes)
        _GOOGLE_JOBS[job_id] = job
        try:
            _write_job_file(job_id, job)
        except Exception:
            logger.exception("Failed writing job file", extra={"job_id": job_id})


def _get_job(job_id: str) -> dict | None:
    with _GOOGLE_JOBS_LOCK:
        job = _GOOGLE_JOBS.get(job_id)
        if job:
            return job
    path = _job_path(job_id)
    if path.exists():
        try:
            job = json.loads(path.read_text())
            with _GOOGLE_JOBS_LOCK:
                _GOOGLE_JOBS[job_id] = job
            return job
        except Exception:
            logger.exception("Failed reading job file", extra={"job_id": job_id})
    return None


def get_photos_with_state() -> list[dict]:
    """Load photos with face results and review state merged."""
    photos = load_photos_manifest()
    face_results = load_json(FACE_RESULTS, {})
    review_state = load_review_state()

    enriched = []
    for p in photos:
        pid = p["id"]
        state = review_state.get(pid, normalize_review_entry("pending"))
        face_count = _face_count(face_results.get(pid, {"face_count": -1}))

        row = dict(p)
        row["face_count"] = face_count
        row["status"] = state.get("status", "pending")
        row["hero_pin"] = bool(state.get("hero_pin", False))
        row["caption"] = (state.get("caption") or "").strip()

        date = p.get("date_taken")
        row["date"] = date[:10].replace(":", "-") if date else None
        enriched.append(row)

    return enriched


def get_counts() -> dict:
    photos = load_photos_manifest()
    review_state = load_review_state()
    changed = False
    for photo in photos:
        if photo["id"] not in review_state:
            review_state[photo["id"]] = normalize_review_entry("pending")
            changed = True
    if changed:
        save_review_state(review_state)

    approved = sum(1 for v in review_state.values() if v.get("status") == "approved")
    rejected = sum(1 for v in review_state.values() if v.get("status") == "rejected")
    pending = sum(1 for v in review_state.values() if v.get("status") == "pending")
    hero = sum(1 for v in review_state.values() if v.get("hero_pin"))
    return {
        "approved": approved,
        "rejected": rejected,
        "pending": pending,
        "hero": hero,
        "total": len(review_state),
    }


def auto_approve_candidates():
    """Auto-approve all detected 2-face candidates."""
    face_results = load_json(FACE_RESULTS, {})
    review_state = load_review_state()

    for photo_id, payload in face_results.items():
        count = _face_count(payload)
        entry = review_state.get(photo_id, normalize_review_entry("pending"))
        entry["status"] = "approved" if count == TARGET_FACE_COUNT else "rejected"
        review_state[photo_id] = entry

    save_review_state(review_state)


def _apply_filter(photos: list[dict], filter_key: str) -> list[dict]:
    if filter_key == "approved":
        return [p for p in photos if p["status"] == "approved"]
    if filter_key == "pending":
        return [p for p in photos if p["status"] == "pending"]
    if filter_key == "rejected":
        return [p for p in photos if p["status"] == "rejected"]
    if filter_key == "hero":
        return [p for p in photos if p["hero_pin"]]
    return photos


def _google_sync_worker(job_id: str):
    job = _get_job(job_id)
    if not job:
        return

    picker: GooglePhotoPicker = job["picker"]
    try:
        _set_job(job_id, status="waiting_selection", message="Waiting for media selection in Google Photos")
        if not picker.poll_session(timeout=900):
            _set_job(job_id, status="error", message="Timed out waiting for Google Photos selection")
            return

        _set_job(job_id, status="syncing", message="Downloading selected photos")
        items = picker.get_media_items()
        paths = picker.download_all(items)

        _set_job(job_id, status="processing", message="Processing imported photos")
        result = import_existing_paths(paths, source_prefix="google")
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        _set_job(
            job_id,
            status="done",
            message="Import complete",
            imported=result["imported"],
            skipped=result["skipped"],
            total=result["total"],
        )
    except Exception as exc:
        _set_job(job_id, status="error", message=str(exc))


def _advance_google_job(job_id: str) -> dict | None:
    job = _get_job(job_id)
    if not job:
        return None
    if job.get("status") in {"done", "error"}:
        return job

    picker_state = job.get("picker_state") or {}
    token = picker_state.get("token")
    session_id = picker_state.get("session_id")
    if not token or not session_id:
        return job

    picker = GooglePhotoPicker.from_saved_state(token=token, session_id=session_id)

    if not job.get("media_items"):
        try:
            session = picker.session_status()
            if not session.get("mediaItemsSet"):
                _set_job(
                    job_id,
                    status="waiting_selection",
                    message="Waiting for you to press Done in Google Photos.",
                )
                _record_job_event(job_id, "waiting_selection", "Selection not completed yet")
                return _get_job(job_id)

            items = picker.get_media_items()
            _set_job(
                job_id,
                status="syncing",
                message=f"Preparing to import {len(items)} selected photos.",
                media_items=items,
                selected_total=len(items),
                batch_cursor=0,
                imported=job.get("imported", 0),
                skipped=job.get("skipped", 0),
            )
            _record_job_event(job_id, "selection_complete", "Google selection completed", selected_total=len(items))
            return _get_job(job_id)
        except Exception as exc:
            _set_job(job_id, status="error", message=str(exc))
            _record_job_event(job_id, "error", "Failed while checking Google session", error=str(exc))
            return _get_job(job_id)

    items = job.get("media_items") or []
    cursor = int(job.get("batch_cursor", 0))
    if cursor >= len(items):
        _set_job(
            job_id,
            status="done",
            message=f"Import complete. Imported {job.get('imported', 0)} photos.",
        )
        _record_job_event(job_id, "done", "Import completed", imported=job.get("imported", 0), skipped=job.get("skipped", 0))
        return _get_job(job_id)

    batch = items[cursor:cursor + _JOB_BATCH_SIZE]
    _set_job(
        job_id,
        status="processing",
        message=f"Importing photos {cursor + 1}-{cursor + len(batch)} of {len(items)}.",
    )
    _record_job_event(job_id, "processing", "Starting import batch", cursor=cursor, batch_size=len(batch))
    try:
        paths = picker.download_all(batch)
        _record_job_event(job_id, "downloaded", "Downloaded Google batch", downloaded=len(paths), cursor=cursor)
        result = import_existing_paths(paths, source_prefix="google")
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

        imported = int(job.get("imported", 0)) + int(result["imported"])
        skipped = int(job.get("skipped", 0)) + int(result["skipped"])
        next_cursor = cursor + len(batch)
        status = "done" if next_cursor >= len(items) else "syncing"
        message = (
            f"Import complete. Imported {imported} photos."
            if status == "done"
            else f"Imported {next_cursor} of {len(items)} selected photos."
        )
        _set_job(
            job_id,
            status=status,
            message=message,
            batch_cursor=next_cursor,
            imported=imported,
            skipped=skipped,
            total=len(items),
        )
        _record_job_event(
            job_id,
            status,
            "Finished import batch",
            next_cursor=next_cursor,
            selected_total=len(items),
            imported=imported,
            skipped=skipped,
            manifest_total=len(load_photos_manifest()),
        )
    except Exception as exc:
        _set_job(job_id, status="error", message=str(exc))
        _record_job_event(job_id, "error", "Batch import failed", error=str(exc), cursor=cursor)
    return _get_job(job_id)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = "magazine-review-secret"

    def current_google_callback_uri() -> str:
        configured = GOOGLE_REDIRECT_URI.strip()
        if configured:
            return configured
        return url_for("api_import_google_callback", _external=True)

    @app.route("/")
    @app.route("/import")
    def import_screen():
        counts = get_counts()
        return render_template(
            "import.html",
            counts=counts,
            active_page="import",
            title="Import Photos",
            google_configured=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            google_status_message=(
                "Private beta. Connect your library in a secure Google window, choose your photos, and return here while they sync."
                if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
                else "Google Photos is not configured for this private studio yet."
            ),
            google_callback_uri=current_google_callback_uri(),
        )

    @app.route("/review")
    @app.route("/review/candidates")
    def review_candidates():
        photos = get_photos_with_state()
        filter_key = request.args.get("filter", "all")
        visible = _apply_filter(photos, filter_key)
        return render_template(
            "review.html",
            photos=visible,
            counts=get_counts(),
            page_type="all",
            active_page="review",
            title="Review Photos",
            active_filter=filter_key,
        )

    @app.route("/review/others")
    def review_others():
        return redirect(url_for("review_candidates"))

    @app.route("/summary")
    def summary():
        photos = get_photos_with_state()
        approved = [p for p in photos if p["status"] == "approved"]
        counts = get_counts()
        story_config = load_story_config()
        pagination = story_config["pagination"]
        estimated_pages = estimate_page_count(
            photo_count=len(approved),
            density=pagination["density"],
            fixed_pages=pagination["fixed_pages"],
            min_pages=pagination["min_pages"],
            max_pages=pagination["max_pages"],
            page_step=pagination["page_step"],
        )
        return render_template(
            "summary.html",
            approved_photos=approved,
            counts=counts,
            estimated_pages=estimated_pages,
            active_page="summary",
            title="Story & Generate",
            story_config=story_config,
        )

    @app.route("/api/import/local", methods=["POST"])
    def api_import_local():
        files = request.files.getlist("photos")
        if not files:
            return jsonify({"success": False, "error": "No files uploaded"}), 400

        result = import_uploaded_files(files)
        return jsonify({"success": True, **result})

    @app.route("/api/import/google/start", methods=["POST"])
    def api_import_google_start():
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            return jsonify(
                {
                    "success": False,
                    "error": "Google Photos is not configured for this deployment yet.",
                }
            ), 400

        job_id = uuid.uuid4().hex
        picker = GooglePhotoPicker()
        auth_url = picker.get_auth_url(
            state=job_id,
            redirect_uri=current_google_callback_uri(),
        )
        _set_job(
            job_id,
            status="auth",
            message="Waiting for you to approve access in Google.",
            picker=picker,
        )
        _record_job_event(job_id, "auth", "Google auth flow started")
        return jsonify({"success": True, "job_id": job_id, "auth_url": auth_url})

    @app.route("/api/import/google/callback")
    @app.route("/oauth/callback")
    def api_import_google_callback():
        job_id = request.args.get("state", "")
        job = _get_job(job_id)
        if not job:
            logger.error("google_job missing_on_callback job_id=%s", job_id)
            return "Unknown or expired Google import job", 400

        picker: GooglePhotoPicker = job["picker"]
        try:
            picker.handle_callback(request.url)
            picker_uri = picker.create_session()
            _set_job(
                job_id,
                status="picker_ready",
                message="Google Photos connected. Pick the photos you want and press Done.",
                picker_uri=picker_uri,
                picker_state={
                    "token": picker.credentials.token,
                    "session_id": picker.session_id,
                },
            )
            _record_job_event(job_id, "picker_ready", "Google callback completed", picker_uri=picker_uri)
        except Exception as exc:
            _set_job(job_id, status="error", message=str(exc))
            _record_job_event(job_id, "error", "Google callback failed", error=str(exc))
            return f"Google auth failed: {exc}", 500

        return render_template(
            "google_callback.html",
            picker_uri=picker_uri,
        )

    @app.route("/api/import/jobs/<job_id>")
    def api_import_job(job_id):
        job = _advance_google_job(job_id)
        if not job:
            return jsonify(
                {
                    "success": False,
                    "error": "Job not found. Hosted imports use short-lived serverless state, so this job may have expired before processing finished.",
                }
            ), 404

        payload = {k: v for k, v in job.items() if k != "picker"}
        payload["success"] = True
        return jsonify(payload)

    @app.route("/api/review/pin-hero", methods=["POST"])
    def api_pin_hero():
        data = request.json or {}
        photo_id = data.get("id")
        hero_pin = bool(data.get("hero_pin", False))
        caption = (data.get("caption") or "").strip()

        review_state = load_review_state()
        entry = review_state.get(photo_id, normalize_review_entry("pending"))
        entry["hero_pin"] = hero_pin
        entry["caption"] = caption
        review_state[photo_id] = entry
        save_review_state(review_state)

        return jsonify({"success": True, "hero_pin": hero_pin, "caption": caption})

    @app.route("/api/toggle", methods=["POST"])
    def api_toggle():
        data = request.json or {}
        photo_id = data.get("id")
        action = data.get("action")

        review_state = load_review_state()
        entry = review_state.get(photo_id, normalize_review_entry("pending"))

        if action == "approve":
            entry["status"] = "approved"
        elif action == "reject":
            entry["status"] = "rejected"

        review_state[photo_id] = entry
        save_review_state(review_state)
        return jsonify({"success": True, "status": entry["status"]})

    @app.route("/api/batch", methods=["POST"])
    def api_batch():
        data = request.json or {}
        action = data.get("action")
        page = data.get("page", "candidates")

        photos = get_photos_with_state()
        review_state = load_review_state()

        target_ids = [p["id"] for p in photos]

        new_status = "approved" if action == "approve_all" else "rejected"
        for pid in target_ids:
            entry = review_state.get(pid, normalize_review_entry("pending"))
            entry["status"] = new_status
            review_state[pid] = entry

        save_review_state(review_state)
        return jsonify({"success": True, "count": len(target_ids)})

    @app.route("/api/counts")
    def api_counts():
        return jsonify(get_counts())

    @app.route("/api/layout/estimate")
    def api_layout_estimate():
        counts = get_counts()
        density = float(request.args.get("density", 1.7))
        min_pages = int(request.args.get("min_pages", 28))
        max_pages = int(request.args.get("max_pages", 72))
        fixed_pages = int(request.args.get("fixed_pages", 8))
        page_step = int(request.args.get("page_step", 4))
        pages = estimate_page_count(
            photo_count=counts["approved"],
            density=density,
            fixed_pages=fixed_pages,
            min_pages=min_pages,
            max_pages=max_pages,
            page_step=page_step,
        )
        return jsonify({"success": True, "approved": counts["approved"], "estimated_pages": pages})

    @app.route("/thumbnail/<photo_id>")
    def serve_thumbnail(photo_id):
        thumb = THUMBNAILS_DIR / f"{photo_id}.jpg"
        if thumb.exists():
            return send_file(thumb, mimetype="image/jpeg")
        return "Not found", 404

    @app.route("/original/<photo_id>")
    def serve_original(photo_id):
        orig = ORIGINALS_DIR / f"{photo_id}.jpg"
        if orig.exists():
            return send_file(orig, mimetype="image/jpeg")
        return "Not found", 404

    @app.route("/generate", methods=["POST"])
    def generate():
        title = request.form.get("title", "Our Love Story")
        subtitle = request.form.get("subtitle", "A Journey Together")
        dedication = request.form.get("dedication", "For you, with all my love")
        style = request.form.get("style", "editorial_luxury")
        pages = request.form.get("pages", "auto")
        min_pages = int(request.form.get("min_pages", 28))
        max_pages = int(request.form.get("max_pages", 72))
        density = float(request.form.get("density", 1.7))
        page_step = int(request.form.get("page_step", 4))
        run_preflight = request.form.get("run_preflight") == "on"

        story_config = {
            "style": style,
            "title": title,
            "subtitle": subtitle,
            "dedication": dedication,
            "flow": "chronological",
            "heroes": [p["id"] for p in get_photos_with_state() if p["hero_pin"]],
            "pagination": {
                "mode": "auto" if str(pages) == "auto" else "manual",
                "min_pages": min_pages,
                "max_pages": max_pages,
                "density": density,
                "fixed_pages": 8,
                "page_step": page_step,
            },
        }
        save_story_config(story_config)

        from magazine.layout.engine import build_layout
        from magazine.pdf.generator import generate_pdf

        try:
            pages_spec = build_layout(
                title=title,
                subtitle=subtitle,
                dedication=dedication,
                style=style,
                pages=pages,
                min_pages=min_pages,
                max_pages=max_pages,
                density=density,
                page_step=page_step,
            )
            output_path = generate_pdf(pages_spec, style=style)

            preflight_note = ""
            if run_preflight:
                from magazine.pdf.preflight import run_preflight as run_pdf_preflight

                report = run_pdf_preflight(output_path, expected_pages=len(pages_spec))
                preflight_note = f" Preflight: {report['status']}."

            flash(
                f"Magazine generated with {len(pages_spec)} pages. Saved to: {output_path}.{preflight_note}",
                "success",
            )
        except Exception as exc:
            flash(f"Error generating magazine: {exc}", "error")

        return redirect(url_for("summary"))

    return app
