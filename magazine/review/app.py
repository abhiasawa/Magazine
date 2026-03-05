"""Flask web UI for reviewing and approving/rejecting photo candidates."""

import json
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash

from magazine.config import (
    PHOTOS_MANIFEST,
    FACE_RESULTS,
    REVIEW_STATE,
    THUMBNAILS_DIR,
    ORIGINALS_DIR,
    TARGET_FACE_COUNT,
)


def load_json(path: Path) -> dict | list:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_photos_with_state() -> list[dict]:
    """Load photos with face results and review state merged."""
    photos = load_json(PHOTOS_MANIFEST)
    if isinstance(photos, dict):
        photos = []
    face_results = load_json(FACE_RESULTS)
    review_state = load_json(REVIEW_STATE)

    enriched = []
    for p in photos:
        pid = p["id"]
        p["face_count"] = face_results.get(pid, -1)
        p["status"] = review_state.get(pid, "pending")
        # Format date for display
        date = p.get("date_taken")
        if date:
            p["date"] = date[:10].replace(":", "-")  # YYYY-MM-DD
        else:
            p["date"] = None
        enriched.append(p)

    return enriched


def get_counts() -> dict:
    review_state = load_json(REVIEW_STATE)
    approved = sum(1 for v in review_state.values() if v == "approved")
    rejected = sum(1 for v in review_state.values() if v == "rejected")
    return {
        "approved": approved,
        "rejected": rejected,
        "total": len(review_state),
    }


def auto_approve_candidates():
    """Auto-approve all 2-face candidates (for --skip-review mode)."""
    face_results = load_json(FACE_RESULTS)
    review_state = load_json(REVIEW_STATE)

    for photo_id, face_count in face_results.items():
        if face_count == TARGET_FACE_COUNT:
            review_state[photo_id] = "approved"
        else:
            review_state[photo_id] = "rejected"

    save_json(REVIEW_STATE, review_state)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = "magazine-review-secret"

    @app.route("/")
    def index():
        return redirect(url_for("review_candidates"))

    @app.route("/review")
    @app.route("/review/candidates")
    def review_candidates():
        photos = get_photos_with_state()
        candidates = [p for p in photos if p["face_count"] == TARGET_FACE_COUNT]
        return render_template(
            "review.html",
            photos=candidates,
            counts=get_counts(),
            page_type="candidates",
            active_page="candidates",
            title="Candidates",
        )

    @app.route("/review/others")
    def review_others():
        photos = get_photos_with_state()
        others = [p for p in photos if p["face_count"] != TARGET_FACE_COUNT]
        return render_template(
            "review.html",
            photos=others,
            counts=get_counts(),
            page_type="others",
            active_page="others",
            title="Other Photos",
        )

    @app.route("/summary")
    def summary():
        photos = get_photos_with_state()
        approved = [p for p in photos if p["status"] == "approved"]
        counts = get_counts()
        # Estimate pages: cover + dedication + back + ~1 page per 1.5 photos + quote pages
        estimated_pages = max(10, 3 + int(len(approved) / 1.5) + max(4, len(approved) // 10))
        return render_template(
            "summary.html",
            approved_photos=approved,
            counts=counts,
            estimated_pages=estimated_pages,
            active_page="summary",
            title="Summary",
        )

    @app.route("/api/toggle", methods=["POST"])
    def api_toggle():
        data = request.json
        photo_id = data.get("id")
        action = data.get("action")

        review_state = load_json(REVIEW_STATE)

        if action == "approve":
            review_state[photo_id] = "approved"
        elif action == "reject":
            review_state[photo_id] = "rejected"

        save_json(REVIEW_STATE, review_state)
        return jsonify({"success": True, "status": review_state[photo_id]})

    @app.route("/api/batch", methods=["POST"])
    def api_batch():
        data = request.json
        action = data.get("action")
        page = data.get("page", "candidates")

        photos = get_photos_with_state()
        review_state = load_json(REVIEW_STATE)
        face_results = load_json(FACE_RESULTS)

        if page == "candidates":
            target_ids = [p["id"] for p in photos if p["face_count"] == TARGET_FACE_COUNT]
        else:
            target_ids = [p["id"] for p in photos if p["face_count"] != TARGET_FACE_COUNT]

        new_status = "approved" if action == "approve_all" else "rejected"
        for pid in target_ids:
            review_state[pid] = new_status

        save_json(REVIEW_STATE, review_state)
        return jsonify({"success": True, "count": len(target_ids)})

    @app.route("/api/counts")
    def api_counts():
        return jsonify(get_counts())

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

        from magazine.layout.engine import build_layout
        from magazine.pdf.generator import generate_pdf

        try:
            pages = build_layout(title=title, subtitle=subtitle, dedication=dedication)
            output_path = generate_pdf(pages)
            flash(f"Magazine generated! Saved to: {output_path}", "success")
        except Exception as e:
            flash(f"Error generating magazine: {e}", "error")

        return redirect(url_for("summary"))

    @app.route("/shutdown", methods=["POST"])
    def shutdown():
        func = request.environ.get("werkzeug.server.shutdown")
        if func:
            func()
        return "Server shutting down..."

    return app
