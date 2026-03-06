# Content Comparison Tool

This tool compares content between two systems using URL pairs from a JSON file. It uses Playwright with Python and is designed to be resilient, scalable, and maintainable.

## Project Structure

```
content-comparison-tool/
├── pyproject.toml          # Poetry project & dependency configuration
├── pytest.ini              # Pytest configuration (JUnit XML output)
├── conftest.py             # Shared pytest fixtures
├── compare_tool.py         # Main comparison engine (entry point)
├── text_normalization.py   # HTML unescape, whitespace collapse, case folding
├── diff_scoring.py         # SequenceMatcher similarity & unified diff helpers
├── data/
│   └── test_data.json      # Input test-case definitions (URL pairs + locators)
├── artifacts/
│   └── content_compare/
│       └── <run_id>/       # Per-run output directory
│           ├── index.html  # Dashboard summarising all cases
│           ├── results.json
│           ├── README.md
│           └── cases/
│               └── <id>/   # Per-case artefacts
│                   ├── a.txt
│                   ├── b.txt
│                   └── diff.txt
├── .github/
│   └── workflows/
│       └── ci.yml          # GitHub Actions CI pipeline
├── venv/                   # Python virtual environment (not committed)
└── README.md
```

## Requirements

- Python 3.8+
- [Poetry](https://python-poetry.org/) (dependency management)
- Playwright browsers (installed via `playwright install`)

## Setup

1. Create and activate a virtual environment:
    ```sh
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS / Linux
    source venv/bin/activate
    ```

2. Install Poetry and project dependencies:
    ```sh
    pip install poetry
    poetry install
    ```

3. Install Playwright browsers:
    ```sh
    python -m playwright install
    ```

## Usage

Run the comparison tool with defaults:

```sh
python compare_tool.py
```

Or override any option via CLI flags:

```sh
python compare_tool.py \
  --input data/test_data.json \
  --output-dir artifacts/content_compare \
  --run-id my_run \
  --timeout-ms 30000 \
  --ignore-case true \
  --max-diff-lines 50
```

The tool will:

1. Load test cases from the input JSON file.
2. Launch a headless Chromium browser via Playwright.
3. For each case, navigate to `url_a` and `url_b`, extract visible text using the configured CSS locators.
4. Normalize extracted text (HTML entity decoding, whitespace collapsing, optional case folding).
5. Compute a similarity score (0.0 – 1.0) using `difflib.SequenceMatcher`.
6. Generate a unified diff of the two texts.
7. Write per-case artefacts (`a.txt`, `b.txt`, `diff.txt`, `meta.json`) and a run-level `results.json` + `index.html` dashboard.

All output is written to `artifacts/content_compare/<run_id>/`.

### Exit codes

| Condition | Default (local) | With `--ci` |
|-----------|-----------------|-------------|
| All cases pass | exit 0 | exit 0 |
| Diff mismatches found | exit 1 | exit 0 |
| Extraction errors | exit 1 | exit 1 |

Use `--fail-on-diff` and `--fail-on-error` to override individually.

### Local file support

URLs in `test_data.json` can be `http(s)://` URLs or local file paths relative
to the JSON file's directory. Local paths are automatically resolved to
`file:///` URIs for Playwright.

## Running Tests

```sh
# Run the full test suite
pytest

# Run tests in parallel (requires pytest-xdist)
pytest -n auto
```

Test results are saved to `results.xml` (JUnit XML) as configured in `pytest.ini`.

## Configuration (CLI flags)

All options are passed via the command line:

| Flag               | Default                        | Description                                        |
|--------------------|--------------------------------|----------------------------------------------------|
| `--input`          | `data/test_data.json`          | Path to the JSON file containing test cases        |
| `--output-dir`     | `artifacts/content_compare`    | Root directory for run output                      |
| `--run-id`         | auto timestamp `YYYYmmdd_HHMMSS` | Unique identifier for the current run            |
| `--timeout-ms`     | `30000`                        | Playwright navigation / locator timeout (ms)       |
| `--ignore-case`    | `true`                         | Lowercase text before comparison (`true`/`false`)  |
| `--max-diff-lines` | `50`                           | Maximum lines included in the unified diff summary |
| `--ci`             | off                            | CI mode: don't fail on diffs, only on errors       |
| `--fail-on-diff`   | `true` (local), `false` (`--ci`) | Exit 1 when diff mismatches found                |
| `--fail-on-error`  | `true`                         | Exit 1 when extraction errors occur                |

## JSON Data Format

The input JSON file must contain an array of objects. Each object represents a single comparison case with the following fields:

| Field       | Type   | Required | Description                                        |
|-------------|--------|----------|----------------------------------------------------|
| `id`        | string | yes      | Unique identifier for the test case                |
| `url_a`     | string | yes      | URL of the first (source) system                   |
| `url_b`     | string | yes      | URL of the second (target) system                  |
| `locator_a` | string | yes      | CSS selector for the element to extract from `url_a` |
| `locator_b` | string | yes      | CSS selector for the element to extract from `url_b` |

### Example

```json
[
  {
    "id": "case_001",
    "url_a": "https://system-a.example.com/page1",
    "url_b": "https://system-b.example.com/page1",
    "locator_a": "#main-content",
    "locator_b": "article[data-testid='cmp-article']"
  }
]
```

## Output / Results

Each run produces a directory at `artifacts/content_compare/<run_id>/` containing:

| Path                        | Description                                                              |
|-----------------------------|--------------------------------------------------------------------------|
| `index.html`                | HTML dashboard listing every case with status, similarity score, and diff |
| `results.json`              | Machine-readable JSON summary of all cases                               |
| `cases/<id>/a.txt`          | Normalized text extracted from `url_a`                                   |
| `cases/<id>/b.txt`          | Normalized text extracted from `url_b`                                   |
| `cases/<id>/diff.txt`       | Unified diff between `a.txt` and `b.txt`                                |
| `cases/<id>/meta.json`      | Timings, URLs, locators, and error info (if any)                         |
| `cases/<id>/failure_a.png`  | Screenshot if extraction from `url_a` failed                             |
| `cases/<id>/failure_b.png`  | Screenshot if extraction from `url_b` failed                             |

### `results.json` Schema

```json
{
  "<case_id>": {
    "status": "PASS | FAIL",
    "similarity_score": 0.95,
    "differences": "unified diff string",
    "timings": {
      "start_time": "ISO-8601",
      "end_time": "ISO-8601"
    },
    "error": "error message (FAIL only)"
  }
}
```

## Architecture

```
test_data.json
      │
      ▼
┌──────────────────┐     ┌──────────────────────────┐     ┌──────────────┐
│ load JSON cases  │──▶│ Playwright (headless)     │──▶│  write output │
└──────────────────┘   │  for each case:            │   │  a.txt, b.txt │
                       │   goto url → wait locator  │   │  diff.txt     │
                       │   inner_text() → normalize │   │  meta.json    │
                       │   score & diff             │   │  results.json │
                       └──────────────────────────┘   │  index.html   │
                                                       └──────────────┘
```

- **Browser lifecycle**: One Chromium instance + context for the entire run; a fresh page per case.
- **Sequential processing**: Cases run one at a time to avoid Playwright thread-safety issues. For parallelism, use `pytest-xdist` or multiprocessing (one browser per process).
- **Text normalisation** (`text_normalization.py`): Decodes HTML entities, collapses whitespace, and optionally lowercases text.
- **Diff scoring** (`diff_scoring.py`): `SequenceMatcher` ratio for similarity; `unified_diff` for human-readable diffs.
- **Failure handling**: On locator timeout or extraction error, a screenshot is saved and the case is marked FAIL with the error message.

## CI / CD

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request:

1. Checks out the repo.
2. Sets up Python and installs dependencies via Poetry.
3. Runs the `pytest` test suite.
4. Executes the content comparison tool.

## Contributing

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-change`.
3. Make your changes and add tests.
4. Run linting: `black . && isort . && flake8`.
5. Open a pull request.

## License

This project is provided as-is for internal use. See the repository owner for licensing details.
