from pathlib import Path

from PIL import Image

from magazine.services.state import normalize_review_entry, normalize_review_state


def test_normalize_review_entry_backward_compat():
    old = normalize_review_entry("approved")
    assert old["status"] == "approved"
    assert old["hero_pin"] is False
    assert old["caption"] == ""

    new = normalize_review_entry({"status": "pending", "hero_pin": True, "caption": " hello "})
    assert new["status"] == "pending"
    assert new["hero_pin"] is True
    assert new["caption"] == "hello"


def test_normalize_review_state_non_dict():
    assert normalize_review_state([]) == {}


def test_import_existing_paths_dedup(monkeypatch, tmp_path):
    import magazine.services.importer as imp
    import magazine.services.state as state

    originals = tmp_path / "originals"
    thumbs = tmp_path / "thumbs"
    originals.mkdir()
    thumbs.mkdir()

    photos_manifest = tmp_path / "photos.json"
    review_state = tmp_path / "review_state.json"
    photo_hashes = tmp_path / "photo_hashes.json"
    face_results = tmp_path / "face_results.json"

    monkeypatch.setattr(imp, "ORIGINALS_DIR", originals)
    monkeypatch.setattr(imp, "THUMBNAILS_DIR", thumbs)
    monkeypatch.setattr(imp, "PHOTO_HASHES", photo_hashes)
    monkeypatch.setattr(imp, "FACE_RESULTS", face_results)

    monkeypatch.setattr(state, "PHOTOS_MANIFEST", photos_manifest)
    monkeypatch.setattr(state, "REVIEW_STATE", review_state)

    src = tmp_path / "sample.jpg"
    Image.new("RGB", (1200, 900), color=(220, 180, 140)).save(src, "JPEG")

    first = imp.import_existing_paths([src], source_prefix="test")
    second = imp.import_existing_paths([src], source_prefix="test")

    assert first["imported"] == 1
    assert second["imported"] == 0
    assert second["skipped"] == 1
    assert photos_manifest.exists()
    assert review_state.exists()
