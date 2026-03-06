from pathlib import Path
from uuid import uuid4

from magazine.review.app import create_app, _advance_google_job, _set_job


def test_review_candidates_shows_all_imported_photos(monkeypatch):
    app = create_app()
    photos = [
        {"id": "a", "face_count": 0, "status": "pending", "hero_pin": False, "caption": "", "date": None},
        {"id": "b", "face_count": -1, "status": "approved", "hero_pin": False, "caption": "", "date": None},
    ]

    monkeypatch.setattr("magazine.review.app.get_photos_with_state", lambda: photos)
    monkeypatch.setattr("magazine.review.app.get_counts", lambda: {"approved": 1, "pending": 1, "hero": 0, "rejected": 0, "total": 2})

    client = app.test_client()
    response = client.get("/review")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "card-a" in body
    assert "card-b" in body


def test_review_others_redirects_to_main_review():
    app = create_app()
    client = app.test_client()

    response = client.get("/review/others")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/review/candidates")


def test_batch_action_applies_to_all_visible_photos(monkeypatch):
    app = create_app()
    photos = [
        {"id": "a", "face_count": 0, "status": "pending", "hero_pin": False, "caption": "", "date": None},
        {"id": "b", "face_count": 3, "status": "pending", "hero_pin": False, "caption": "", "date": None},
    ]
    saved = {}

    monkeypatch.setattr("magazine.review.app.get_photos_with_state", lambda: photos)
    monkeypatch.setattr("magazine.review.app.load_review_state", lambda: {})
    monkeypatch.setattr("magazine.review.app.save_review_state", lambda state: saved.update(state))

    client = app.test_client()
    response = client.post("/api/batch", json={"action": "approve_all", "page": "candidates"})

    assert response.status_code == 200
    assert saved["a"]["status"] == "approved"
    assert saved["b"]["status"] == "approved"


def test_google_job_selection_and_processing_are_split(monkeypatch):
    job_id = f"job-selection-split-{uuid4().hex}"
    items = [
        {
            "id": str(i),
            "mediaFile": {
                "baseUrl": f"https://example.com/{i}",
                "mediaFileMetadata": {"width": 1, "height": 1},
            },
        }
        for i in range(4)
    ]

    _set_job(job_id, status="picker_ready", picker_state={"token": "tok", "session_id": "sid"})

    class FakePicker:
        def session_status(self):
            return {"mediaItemsSet": True}

        def get_media_items(self):
            return items

        def download_all(self, batch):
            return [Path(f"/tmp/{entry['id']}.jpg") for entry in batch]

    monkeypatch.setattr("magazine.review.app.GooglePhotoPicker.from_saved_state", lambda **_: FakePicker())
    monkeypatch.setattr(
        "magazine.review.app.import_existing_paths",
        lambda paths, source_prefix: {"imported": len(paths), "skipped": 0, "total": len(paths)},
    )
    monkeypatch.setattr("magazine.review.app.load_photos_manifest", lambda: [{"id": "x"}])

    first = dict(_advance_google_job(job_id))
    second = _advance_google_job(job_id)

    assert first["status"] == "syncing"
    assert first["selected_total"] == 4
    assert first["batch_cursor"] == 0
    assert second["batch_cursor"] == 2
    assert second["status"] == "syncing"
