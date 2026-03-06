"""PDF preflight checks and proof rendering."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from magazine.config import OUTPUT_DIR, PREFLIGHT_REPORT


def _check(status: str, name: str, details: str) -> dict:
    return {
        "status": status,
        "name": name,
        "details": details,
    }


def _load_page_count(pdf_path: Path) -> tuple[int | None, str | None]:
    try:
        from pypdf import PdfReader
    except Exception:
        return None, "pypdf is not installed; skipped exact page-count check"

    reader = PdfReader(str(pdf_path))
    return len(reader.pages), None


def _render_proofs(pdf_path: Path, proof_dir: Path) -> tuple[int, list[Path], str | None]:
    if shutil.which("pdftoppm") is None:
        return 0, [], "pdftoppm not installed; skipped PNG proof rendering"

    proof_dir.mkdir(parents=True, exist_ok=True)
    prefix = proof_dir / "page"
    cmd = [
        "pdftoppm",
        "-png",
        str(pdf_path),
        str(prefix),
    ]
    subprocess.run(cmd, check=True)
    pages = sorted(proof_dir.glob("page-*.png"))
    return len(pages), pages, None


def _proof_dimension_summary(pages: list[Path]) -> str:
    if not pages:
        return "No proof pages rendered"

    widths = []
    heights = []
    for path in pages:
        with Image.open(path) as img:
            widths.append(img.width)
            heights.append(img.height)

    return (
        f"Rendered {len(pages)} page proofs; min dimensions "
        f"{min(widths)}x{min(heights)} px, max {max(widths)}x{max(heights)} px"
    )


def run_preflight(pdf_path: str | Path, expected_pages: int | None = None) -> dict:
    pdf = Path(pdf_path)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdf_path": str(pdf),
        "checks": [],
        "proof_dir": str(OUTPUT_DIR / "proofs"),
    }

    if not pdf.exists():
        report["checks"].append(_check("fail", "pdf_exists", f"Missing file: {pdf}"))
        report["status"] = "fail"
        with open(PREFLIGHT_REPORT, "w") as f:
            json.dump(report, f, indent=2)
        return report

    size_mb = pdf.stat().st_size / (1024 * 1024)
    report["size_mb"] = round(size_mb, 2)
    if size_mb < 1:
        report["checks"].append(_check("warn", "pdf_size", f"Small output size ({size_mb:.2f} MB)."))
    else:
        report["checks"].append(_check("pass", "pdf_size", f"File size: {size_mb:.2f} MB"))

    page_count, page_count_warn = _load_page_count(pdf)
    if page_count is None:
        report["checks"].append(_check("warn", "page_count", page_count_warn or "Unknown page count"))
    else:
        report["page_count"] = page_count
        report["checks"].append(_check("pass", "page_count", f"Detected {page_count} pages"))
        if expected_pages is not None and expected_pages != page_count:
            report["checks"].append(
                _check(
                    "warn",
                    "expected_pages",
                    f"Expected {expected_pages}, but PDF has {page_count}",
                )
            )

    proof_dir = OUTPUT_DIR / "proofs"
    proof_count, proof_paths, proof_warn = _render_proofs(pdf, proof_dir)
    if proof_warn:
        report["checks"].append(_check("warn", "proof_render", proof_warn))
    else:
        report["checks"].append(_check("pass", "proof_render", f"Rendered {proof_count} proof PNGs"))
        report["checks"].append(_check("pass", "proof_dimensions", _proof_dimension_summary(proof_paths)))

    failed = any(item["status"] == "fail" for item in report["checks"])
    warned = any(item["status"] == "warn" for item in report["checks"])
    report["status"] = "fail" if failed else ("warn" if warned else "pass")

    with open(PREFLIGHT_REPORT, "w") as f:
        json.dump(report, f, indent=2)

    summary_path = OUTPUT_DIR / "preflight_summary.txt"
    with open(summary_path, "w") as f:
        f.write(f"Preflight status: {report['status']}\n")
        for item in report["checks"]:
            f.write(f"[{item['status']}] {item['name']}: {item['details']}\n")

    return report
