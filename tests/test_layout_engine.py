from magazine.layout.engine import estimate_page_count, build_layout, load_approved_photos


def _fake_photo(idx: int, hero: bool = False) -> dict:
    return {
        "id": f"p{idx}",
        "original": f"/tmp/p{idx}.jpg",
        "thumbnail": f"/tmp/p{idx}_thumb.jpg",
        "width": 4000,
        "height": 3000,
        "date_taken": f"2024:01:{idx+1:02d} 12:00:00",
        "hero_pin": hero,
        "faces": [],
    }


def test_estimate_page_count_clamp_and_rounding():
    assert estimate_page_count(photo_count=0) == 28
    assert estimate_page_count(photo_count=30, density=1.7, fixed_pages=8, min_pages=28, max_pages=72, page_step=4) == 28
    assert estimate_page_count(photo_count=95, density=1.7, fixed_pages=8, min_pages=28, max_pages=72, page_step=4) == 64
    assert estimate_page_count(photo_count=999, density=1.7, fixed_pages=8, min_pages=28, max_pages=72, page_step=4) == 72


def test_build_layout_uses_target_pages_and_places_hero(monkeypatch):
    photos = [_fake_photo(i, hero=i in {2, 7, 11}) for i in range(16)]
    monkeypatch.setattr("magazine.layout.engine.load_approved_photos", lambda: photos)

    pages = build_layout(
        title="Test",
        subtitle="Sub",
        dedication="Ded",
        pages=28,
        min_pages=28,
        max_pages=72,
    )

    assert len(pages) == 28
    hero_ids = {p["id"] for page in pages for p in page.photos if p.get("hero_pin")}
    assert {"p2", "p7", "p11"}.issubset(hero_ids)


def test_build_layout_rounds_manual_pages(monkeypatch):
    photos = [_fake_photo(i) for i in range(20)]
    monkeypatch.setattr("magazine.layout.engine.load_approved_photos", lambda: photos)

    pages = build_layout(pages=31)
    assert len(pages) == 32


def test_load_approved_photos_uses_pending_items(monkeypatch, tmp_path):
    import magazine.layout.engine as engine

    photos_manifest = tmp_path / "photos.json"
    manifest_rows = [
        {"id": "a", "date_taken": "2026:01:01 10:00:00", "width": 1200, "height": 900, "original": "a.jpg"},
        {"id": "b", "date_taken": "2026:01:02 10:00:00", "width": 1200, "height": 900, "original": "b.jpg"},
    ]
    photos_manifest.write_text("[]")

    monkeypatch.setattr(engine, "PHOTOS_MANIFEST", photos_manifest)
    monkeypatch.setattr(
        "magazine.layout.engine.load_json",
        lambda path, default: manifest_rows if path == photos_manifest else {},
    )
    monkeypatch.setattr(
        "magazine.layout.engine.load_review_state",
        lambda: {"a": {"status": "pending"}, "b": {"status": "approved"}},
    )

    photos = load_approved_photos()

    assert [photo["id"] for photo in photos] == ["a", "b"]
