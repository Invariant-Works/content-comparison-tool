"""Content Comparison Tool — extracts visible text from two URLs via Playwright,
normalises it, computes a similarity score, and writes per-case artefacts plus a
run-level dashboard.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from text_normalization import normalize_text
from diff_scoring import calculate_similarity_score, summarize_differences
from html_diff import generate_diff_html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_url(raw_url: str, base_dir: Path) -> str:
    """Return a URL string Playwright can navigate to.

    * http(s) URLs are returned unchanged.
    * Everything else is treated as a file path relative to *base_dir* and
      converted to a ``file:///`` URI.
    """
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    resolved = (base_dir / raw_url).resolve()
    return resolved.as_uri()


def extract_visible_text(page, url: str, locator: str, timeout_ms: int) -> tuple:
    """Navigate *page* to *url*, wait for *locator*, and return
    ``(raw_text, locator_count)``.

    Raises on navigation or locator timeout so the caller can record a FAIL.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    loc = page.locator(locator)
    count = loc.count()
    loc.first.wait_for(state="visible", timeout=timeout_ms)
    raw = loc.first.inner_text(timeout=timeout_ms)
    return raw, count


def load_json_data(file_path: str) -> list:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Per-case processing
# ---------------------------------------------------------------------------

def process_case(case: dict, context, *, base_dir: Path, output_dir: str,
                 run_id: str, timeout_ms: int, ignore_case: bool,
                 max_diff_lines: int) -> dict:
    """Process a single comparison case and return a result dict."""
    case_id = case["id"]
    case_dir = os.path.join(output_dir, run_id, "cases", case_id)
    os.makedirs(case_dir, exist_ok=True)

    resolved_a = resolve_url(case["url_a"], base_dir)
    resolved_b = resolve_url(case["url_b"], base_dir)
    locator_a = case["locator_a"]
    locator_b = case["locator_b"]

    start_time = datetime.now(timezone.utc).isoformat()

    meta = {
        "resolved_url_a": resolved_a,
        "resolved_url_b": resolved_b,
        "locator_a": locator_a,
        "locator_b": locator_b,
        "locator_count_a": 0,
        "locator_count_b": 0,
        "raw_preview_a": "",
        "raw_preview_b": "",
    }

    page = context.new_page()
    try:
        # --- Extract A ---
        try:
            raw_a, count_a = extract_visible_text(page, resolved_a, locator_a,
                                                  timeout_ms)
            meta["locator_count_a"] = count_a
            meta["raw_preview_a"] = raw_a[:200]
        except Exception as exc_a:
            meta["error_a"] = str(exc_a)
            page.screenshot(path=os.path.join(case_dir, "failure_a.png"))
            end_time = datetime.now(timezone.utc).isoformat()
            meta["timings"] = {"start_time": start_time, "end_time": end_time}
            _write_json(os.path.join(case_dir, "meta.json"), meta)
            return {
                "status": "FAIL",
                "error": f"Extraction A failed: {exc_a}",
                "timings": meta["timings"],
            }

        # --- Extract B ---
        try:
            raw_b, count_b = extract_visible_text(page, resolved_b, locator_b,
                                                  timeout_ms)
            meta["locator_count_b"] = count_b
            meta["raw_preview_b"] = raw_b[:200]
        except Exception as exc_b:
            meta["error_b"] = str(exc_b)
            page.screenshot(path=os.path.join(case_dir, "failure_b.png"))
            end_time = datetime.now(timezone.utc).isoformat()
            meta["timings"] = {"start_time": start_time, "end_time": end_time}
            _write_json(os.path.join(case_dir, "meta.json"), meta)
            return {
                "status": "FAIL",
                "error": f"Extraction B failed: {exc_b}",
                "timings": meta["timings"],
            }

        # --- Normalize ---
        text_a = normalize_text(raw_a, ignore_case=ignore_case)
        text_b = normalize_text(raw_b, ignore_case=ignore_case)

        # --- Score & diff ---
        similarity = calculate_similarity_score(text_a, text_b)
        differences = summarize_differences(text_a, text_b, max_diff_lines)
        status = "PASS" if similarity == 1.0 else "FAIL"

        end_time = datetime.now(timezone.utc).isoformat()
        meta["timings"] = {"start_time": start_time, "end_time": end_time}

        # --- HTML diff ---
        diff_html = generate_diff_html(
            case_id=case_id,
            url_a=resolved_a,
            url_b=resolved_b,
            locator_a=locator_a,
            locator_b=locator_b,
            text_a=text_a,
            text_b=text_b,
            similarity=similarity,
        )

        # --- Write per-case artefacts ---
        _write_text(os.path.join(case_dir, "a.txt"), text_a)
        _write_text(os.path.join(case_dir, "b.txt"), text_b)
        _write_text(os.path.join(case_dir, "diff.txt"), differences)
        _write_text(os.path.join(case_dir, "diff.html"), diff_html)
        _write_json(os.path.join(case_dir, "meta.json"), meta)

        return {
            "status": status,
            "similarity_score": similarity,
            "differences": differences,
            "timings": meta["timings"],
        }

    finally:
        page.close()


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def generate_dashboard(results: dict, run_dir: str) -> None:
    """Write a simple HTML dashboard summarising all cases."""
    path = os.path.join(run_dir, "index.html")
    rows = []
    max_preview = 15  # max diff lines shown inline
    for cid, r in results.items():
        score = r.get("similarity_score", "N/A")
        if isinstance(score, float):
            score = f"{score:.4f}"
        status_class = "pass" if r["status"] == "PASS" else "fail"
        error = r.get("error", "")
        # Truncate inline diff preview
        raw_diff = r.get("differences", "")
        diff_lines = raw_diff.splitlines()
        if len(diff_lines) > max_preview:
            preview = "\n".join(diff_lines[:max_preview])
            preview += f'\n… ({len(diff_lines) - max_preview} more lines — '
            preview += f'<a href="cases/{cid}/diff.html">see diff view</a>)'
        else:
            preview = _esc(raw_diff)
        # Diff view link
        diff_link = f'<a href="cases/{cid}/diff.html">View Diff</a>'
        rows.append(
            f'<tr class="{status_class}">'
            f'<td><a href="cases/{cid}/a.txt">{cid}</a></td>'
            f'<td>{r["status"]}</td>'
            f'<td>{score}</td>'
            f'<td>{diff_link}</td>'
            f'<td><pre>{preview}</pre></td>'
            f'<td>{_esc(error)}</td></tr>'
        )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>\n"
        "<title>Content Compare — Run Results</title>\n"
        "<style>\n"
        "body{font-family:system-ui,sans-serif;margin:20px}\n"
        "table{border-collapse:collapse;width:100%}\n"
        "th,td{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top}\n"
        "pre{margin:0;white-space:pre-wrap;font-size:12px;max-height:300px;overflow:auto}\n"
        ".pass td:nth-child(2){color:green;font-weight:bold}\n"
        ".fail td:nth-child(2){color:red;font-weight:bold}\n"
        "a{color:#0969da}\n"
        "</style></head><body>\n"
        "<h1>Content Comparison Results</h1>\n"
        "<table><thead><tr>"
        "<th>Case ID</th><th>Status</th><th>Similarity</th>"
        "<th>Diff View</th><th>Diff Preview</th><th>Error</th>"
        "</tr></thead><tbody>\n"
        + "\n".join(rows)
        + "\n</tbody></table></body></html>"
    )
    _write_text(path, html)


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Content Comparison Tool")
    p.add_argument("--input", default="data/test_data.json",
                   help="Path to JSON test-case file (default: data/test_data.json)")
    p.add_argument("--output-dir", default="artifacts/content_compare",
                   help="Root output directory (default: artifacts/content_compare)")
    p.add_argument("--run-id", default=None,
                   help="Run identifier (default: YYYYmmdd_HHMMSS timestamp)")
    p.add_argument("--timeout-ms", type=int, default=30000,
                   help="Playwright timeout in milliseconds (default: 30000)")
    p.add_argument("--ignore-case", type=str, default="true",
                   choices=["true", "false"],
                   help="Lowercase text before comparison (default: true)")
    p.add_argument("--max-diff-lines", type=int, default=50,
                   help="Max lines in unified diff summary (default: 50)")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    args = parse_args(argv)

    input_file = args.input
    output_dir = args.output_dir
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    timeout_ms = args.timeout_ms
    ignore_case = args.ignore_case == "true"
    max_diff_lines = args.max_diff_lines

    # Resolve base dir for local file paths in test_data.json
    base_dir = Path(input_file).resolve().parent

    # Load cases
    cases = load_json_data(input_file)
    print(f"Loaded {len(cases)} case(s) from {input_file}")

    run_dir = os.path.join(output_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        for case in cases:
            case_id = case["id"]
            print(f"  Processing {case_id} …", end=" ", flush=True)
            result = process_case(
                case, context,
                base_dir=base_dir,
                output_dir=output_dir,
                run_id=run_id,
                timeout_ms=timeout_ms,
                ignore_case=ignore_case,
                max_diff_lines=max_diff_lines,
            )
            results[case_id] = result
            score = result.get("similarity_score", "—")
            if isinstance(score, float):
                score = f"{score:.4f}"
            print(f"{result['status']}  (similarity {score})")

        context.close()
        browser.close()

    # Write run-level artefacts
    _write_json(os.path.join(run_dir, "results.json"), results)
    generate_dashboard(results, run_dir)

    print(f"\nResults written to {run_dir}/")
    print(f"  results.json   — machine-readable summary")
    print(f"  index.html     — HTML dashboard")

    # Return non-zero if any case failed
    any_fail = any(r["status"] == "FAIL" for r in results.values())
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
