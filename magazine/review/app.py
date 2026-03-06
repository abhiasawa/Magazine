"""Google Photos only Flask workflow for Magazine."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for

from magazine.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    ORIGINALS_DIR,
    OUTPUT_DIR,
    THUMBNAILS_DIR,
    WORKSPACE,
)
from magazine.layout.engine import build_layout, estimate_page_count
from magazine.services.importer import import_existing_paths
from magazine.services.state import (
    load_photos_manifest,
    load_story_config,
    normalize_review_entry,
    save_review_state,
    save_story_config,
)
from magazine.sources.google_picker import GooglePhotoPicker

logger = logging.getLogger(__name__)


def _reset_workspace():
    for child in WORKSPACE.iterdir():
        if child.name == "output":
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)

    for child in OUTPUT_DIR.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)

    for directory in (ORIGINALS_DIR, THUMBNAILS_DIR, WORKSPACE / "print", OUTPUT_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _approve_all_imported():
    state = {
        photo["id"]: normalize_review_entry({"status": "approved", "hero_pin": False, "caption": ""})
        for photo in load_photos_manifest()
    }
    save_review_state(state)


def _download_and_import_google_selection(token: str, session_id: str) -> dict:
    picker = GooglePhotoPicker.from_saved_state(token=token, session_id=session_id)
    items = picker.get_media_items()
    if not items:
        raise ValueError("No photos were selected in Google Photos.")

    _reset_workspace()

    total_imported = 0
    total_skipped = 0
    batch_size = 8

    for cursor in range(0, len(items), batch_size):
        batch = items[cursor:cursor + batch_size]
        downloaded_paths = picker.download_all(batch)
        result = import_existing_paths(downloaded_paths, source_prefix="google")
        total_imported += int(result.get("imported", 0))
        total_skipped += int(result.get("skipped", 0))
        for path in downloaded_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                logger.warning("failed_to_remove_temp_google_file path=%s", path)

    _approve_all_imported()
    return {
        "selected_total": len(items),
        "imported": total_imported,
        "skipped": total_skipped,
    }


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
        return render_template(
            "import.html",
            title="Magazine",
            active_page="import",
            google_configured=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
            story_config=load_story_config(),
        )

    @app.route("/review")
    @app.route("/review/candidates")
    @app.route("/review/others")
    @app.route("/summary")
    def legacy_routes():
        return redirect(url_for("import_screen"))

    @app.route("/api/import/google/start", methods=["POST"])
    def api_import_google_start():
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            return jsonify(
                {
                    "success": False,
                    "error": "Google Photos is not configured for this deployment.",
                }
            ), 400

        picker = GooglePhotoPicker()
        auth_url = picker.get_auth_url(
            state="magazine-google",
            redirect_uri=current_google_callback_uri(),
        )
        return jsonify({"success": True, "auth_url": auth_url})

    @app.route("/api/import/google/callback")
    @app.route("/oauth/callback")
    def api_import_google_callback():
        picker = GooglePhotoPicker()
        try:
            picker.handle_callback(request.url, redirect_uri=current_google_callback_uri())
            picker_uri = picker.create_session()
        except Exception as exc:
            logger.exception("google_auth_failed")
            return f"Google auth failed: {exc}", 500

        return render_template(
            "google_callback.html",
            picker_uri=picker_uri,
            google_token=picker.credentials.token,
            google_session_id=picker.session_id,
            google_state=request.args.get("state", ""),
        )

    @app.route("/api/google/status", methods=["POST"])
    def api_google_status():
        data = request.get_json(force=True, silent=True) or {}
        token = (data.get("token") or "").strip()
        session_id = (data.get("session_id") or "").strip()
        if not token or not session_id:
            return jsonify({"success": False, "error": "Missing Google session details."}), 400

        try:
            picker = GooglePhotoPicker.from_saved_state(token=token, session_id=session_id)
            session = picker.session_status()
            if not session.get("mediaItemsSet"):
                return jsonify(
                    {
                        "success": True,
                        "status": "waiting_selection",
                        "message": "Waiting for you to press Done in Google Photos.",
                    }
                )

            items = picker.get_media_items()
            return jsonify(
                {
                    "success": True,
                    "status": "ready",
                    "message": f"{len(items)} photos selected and ready to generate.",
                    "selected_total": len(items),
                }
            )
        except Exception as exc:
            logger.exception("google_status_failed")
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/layout/estimate")
    def api_layout_estimate():
        selected_total = int(request.args.get("selected_total", 0))
        density = float(request.args.get("density", 1.7))
        min_pages = int(request.args.get("min_pages", 28))
        max_pages = int(request.args.get("max_pages", 72))
        fixed_pages = int(request.args.get("fixed_pages", 8))
        page_step = int(request.args.get("page_step", 4))
        pages = estimate_page_count(
            photo_count=selected_total,
            density=density,
            fixed_pages=fixed_pages,
            min_pages=min_pages,
            max_pages=max_pages,
            page_step=page_step,
        )
        return jsonify({"success": True, "selected_total": selected_total, "estimated_pages": pages})

    @app.route("/api/review/pin-hero", methods=["POST"])
    @app.route("/api/toggle", methods=["POST"])
    @app.route("/api/batch", methods=["POST"])
    def disabled_review_actions():
        return jsonify({"success": False, "error": "Review controls are not used in this flow."}), 400

    @app.route("/generate", methods=["POST"])
    def generate():
        title = (request.form.get("title") or "Magazine").strip()
        subtitle = (request.form.get("subtitle") or "").strip()
        dedication = (request.form.get("dedication") or "").strip()
        style = request.form.get("style", "editorial_luxury")
        pages = request.form.get("pages", "auto")
        min_pages = int(request.form.get("min_pages", 28))
        max_pages = int(request.form.get("max_pages", 72))
        density = float(request.form.get("density", 1.7))
        page_step = int(request.form.get("page_step", 4))
        run_preflight = request.form.get("run_preflight") == "on"
        google_token = (request.form.get("google_token") or "").strip()
        google_session_id = (request.form.get("google_session_id") or "").strip()

        if not google_token or not google_session_id:
            flash("Connect Google Photos and finish your selection before generating.", "error")
            return redirect(url_for("import_screen"))

        story_config = {
            "style": style,
            "title": title,
            "subtitle": subtitle,
            "dedication": dedication,
            "flow": "chronological",
            "heroes": [],
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

        try:
            import_result = _download_and_import_google_selection(google_token, google_session_id)
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

            from magazine.pdf.generator import generate_pdf

            output_path = generate_pdf(pages_spec, style=style)

            if run_preflight:
                from magazine.pdf.preflight import run_preflight as run_pdf_preflight

                run_pdf_preflight(output_path, expected_pages=len(pages_spec))

            logger.info(
                "magazine_generated selected=%s imported=%s skipped=%s pages=%s",
                import_result["selected_total"],
                import_result["imported"],
                import_result["skipped"],
                len(pages_spec),
            )
            return send_file(
                output_path,
                mimetype="application/pdf",
                as_attachment=True,
                download_name="Magazine.pdf",
            )
        except Exception as exc:
            logger.exception("magazine_generate_failed")
            flash(f"Error generating magazine: {exc}", "error")
            return redirect(url_for("import_screen"))

    return app
