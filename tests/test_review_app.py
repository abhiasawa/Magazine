from pathlib import Path

from magazine.review.app import create_app, _google_verifier_cookie_name


def test_legacy_review_routes_redirect_to_import():
    app = create_app()
    client = app.test_client()

    for route in ("/review", "/review/candidates", "/review/others", "/summary"):
        response = client.get(route)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/import")


def test_review_action_endpoints_are_disabled():
    app = create_app()
    client = app.test_client()

    for route in ("/api/batch", "/api/toggle", "/api/review/pin-hero"):
        response = client.post(route, json={})
        assert response.status_code == 400


def test_google_status_reports_selection_ready(monkeypatch):
    app = create_app()

    class FakePicker:
        def session_status(self):
            return {"mediaItemsSet": True}

        def get_media_items(self):
            return [{"id": "1"}, {"id": "2"}, {"id": "3"}]

    monkeypatch.setattr("magazine.review.app.GooglePhotoPicker.from_saved_state", lambda **_: FakePicker())

    client = app.test_client()
    response = client.post("/api/google/status", json={"token": "tok", "session_id": "sid"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["selected_total"] == 3


def test_google_start_sets_pkce_cookie(monkeypatch):
    app = create_app()
    client = app.test_client()

    class FakePicker:
        def start_auth(self, state=None, redirect_uri=None):
            assert state
            return "https://accounts.google.com/o/oauth2/auth?state=" + state, "verifier-123"

    monkeypatch.setattr("magazine.review.app.GooglePhotoPicker", lambda: FakePicker())
    monkeypatch.setattr("magazine.review.app.GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr("magazine.review.app.GOOGLE_CLIENT_SECRET", "client-secret")

    response = client.post("/api/import/google/start")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    state = payload["auth_url"].split("state=")[-1]
    set_cookie = response.headers.get("Set-Cookie", "")
    assert _google_verifier_cookie_name(state) in set_cookie
    assert "verifier-123" in set_cookie


def test_google_callback_uses_pkce_cookie(monkeypatch):
    app = create_app()
    client = app.test_client()
    captured = {}

    class FakePicker:
        credentials = type("Creds", (), {"token": "tok"})()
        session_id = "session-123"

        def handle_callback(self, authorization_response, redirect_uri=None, code_verifier=None):
            captured["authorization_response"] = authorization_response
            captured["redirect_uri"] = redirect_uri
            captured["code_verifier"] = code_verifier

        def create_session(self):
            return "https://photos.google.com/picker"

    monkeypatch.setattr("magazine.review.app.GooglePhotoPicker", lambda: FakePicker())

    state = "abc123"
    client.set_cookie(_google_verifier_cookie_name(state), "verifier-xyz", domain="localhost")
    response = client.get(f"/oauth/callback?state={state}&code=sample-code")

    assert response.status_code == 200
    assert captured["code_verifier"] == "verifier-xyz"
    assert _google_verifier_cookie_name(state) in response.headers.get("Set-Cookie", "")


def test_generate_requires_google_selection():
    app = create_app()
    client = app.test_client()

    response = client.post("/generate", data={"title": "Magazine"}, follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/import")


def test_generate_runs_google_selection_to_pdf(monkeypatch, tmp_path):
    app = create_app()
    client = app.test_client()

    pdf_path = tmp_path / "Magazine.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")

    monkeypatch.setattr(
        "magazine.review.app._download_and_import_google_selection",
        lambda token, session_id: {"selected_total": 5, "imported": 5, "skipped": 0},
    )
    monkeypatch.setattr("magazine.review.app.build_layout", lambda **_: ["page-1", "page-2"])
    monkeypatch.setattr("magazine.pdf.generator.generate_pdf", lambda pages, style=None: pdf_path)

    response = client.post(
        "/generate",
        data={
            "title": "Patricia & Robert",
            "subtitle": "Rome",
            "dedication": "A quiet line",
            "google_token": "tok",
            "google_session_id": "sid",
            "style": "editorial_luxury",
            "pages": "auto",
            "density": "1.7",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-1.4")
