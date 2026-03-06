from magazine.review.app import create_app


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
