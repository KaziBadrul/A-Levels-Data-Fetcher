#!/usr/bin/env python3

import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "data"

DOWNLOAD_DELAY = 0.5
TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
}

UNITS = {
    "WPH11": {
        "page": (
            "https://www.physicsandmathstutor.com/"
            "past-papers/a-level-physics/edexcel-unit-1/"
        ),
        "expected_path": "/Edexcel-IAL/2018-spec/Unit-1/",
    },
    "WPH12": {
        "page": (
            "https://www.physicsandmathstutor.com/"
            "past-papers/a-level-physics/edexcel-unit-2/"
        ),
        "expected_path": "/Edexcel-IAL/2018-spec/Unit-2/",
    },
}

MONTH_TO_FOLDER = {
    "January": "JAN",
    "June": "MAY_JUNE",
    "October": "OCT",
}


# ============================================================
# SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# HELPERS
# ============================================================

def extract_real_pdf_url(href):
    """
    PMT normally gives links like:

    https://www.physicsandmathstutor.com/pdf-pages/
        ?pdf=https%3A%2F%2Fpmt.physicsandmathstutor.com%2F...

    This extracts the actual PDF URL.
    """

    if not href:
        return None

    # Already a direct PDF URL
    if href.lower().endswith(".pdf"):
        return href

    parsed = urlparse(href)
    query = parse_qs(parsed.query)

    pdf_values = query.get("pdf")

    if not pdf_values:
        return None

    return unquote(pdf_values[0])


def parse_paper_name(text):
    """
    Examples:

        January 2025 (IAL) QP
        June 2024 (IAL) MS
        October 2023 (IAL) QP

    Returns:

        {
            "month": "January",
            "year": 2025,
            "type": "QP"
        }

    Specimen papers are intentionally ignored.
    """

    text = " ".join(text.split())

    pattern = (
        r"\b"
        r"(January|June|October)"
        r"\s+"
        r"(20\d{2})"
        r"\s*"
        r"\(IAL\)"
        r"\s*"
        r"(QP|MS)"
        r"\b"
    )

    match = re.search(pattern, text, re.IGNORECASE)

    if not match:
        return None

    month = match.group(1).capitalize()
    year = int(match.group(2))
    paper_type = match.group(3).upper()

    return {
        "month": month,
        "year": year,
        "type": paper_type,
    }


def is_expected_pdf(pdf_url, expected_path):
    """
    Protects us from accidentally downloading legacy WPH0/6PH0
    papers or unrelated files from the page.
    """

    if not pdf_url:
        return False

    decoded = unquote(pdf_url)

    if expected_path not in decoded:
        return False

    if not decoded.lower().endswith(".pdf"):
        return False

    return True


def valid_pdf_file(path):
    """
    Check whether an existing local file really looks like a PDF.
    """

    if not path.exists():
        return False

    try:
        if path.stat().st_size < 100:
            return False

        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"

    except OSError:
        return False


# ============================================================
# DISCOVERY
# ============================================================

def discover_papers(unit_code, config):
    """
    Scrape the PMT Unit page and discover all current-specification
    WPH11/WPH12 question papers and mark schemes.
    """

    page_url = config["page"]
    expected_path = config["expected_path"]

    print()
    print(f"Scanning {unit_code}...")
    print(f"  {page_url}")

    try:
        response = session.get(
            page_url,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

    except requests.RequestException as e:
        print(f"ERROR: Could not load {unit_code} page:")
        print(f"  {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    discovered = []

    for link in soup.find_all("a", href=True):

        text = link.get_text(
            " ",
            strip=True,
        )

        metadata = parse_paper_name(text)

        if metadata is None:
            continue

        href = link.get("href")

        real_pdf_url = extract_real_pdf_url(href)

        if not is_expected_pdf(
            real_pdf_url,
            expected_path,
        ):
            continue

        metadata["unit"] = unit_code
        metadata["url"] = real_pdf_url
        metadata["link_text"] = text

        discovered.append(metadata)

    # Remove duplicate links if PMT happens to expose the same
    # paper more than once.
    unique = {}

    for paper in discovered:

        key = (
            paper["unit"],
            paper["year"],
            paper["month"],
            paper["type"],
        )

        unique[key] = paper

    discovered = list(unique.values())

    discovered.sort(
        key=lambda x: (
            x["year"],
            month_sort_value(x["month"]),
            x["type"],
        )
    )

    print(
        f"  Found {len(discovered)} current-specification files."
    )

    return discovered


def month_sort_value(month):
    order = {
        "January": 1,
        "June": 2,
        "October": 3,
    }

    return order.get(month, 99)


# ============================================================
# LOCAL PATH
# ============================================================

def get_destination(paper):
    """
    Example:

        data/
        └── WPH11/
            └── 2025_JAN/
                ├── question.pdf
                └── mark_scheme.pdf
    """

    unit = paper["unit"]
    year = paper["year"]
    month = paper["month"]
    paper_type = paper["type"]

    session_name = MONTH_TO_FOLDER[month]

    folder = (
        OUTPUT_DIR
        / unit
        / f"{year}_{session_name}"
    )

    if paper_type == "QP":
        filename = "question.pdf"

    elif paper_type == "MS":
        filename = "mark_scheme.pdf"

    else:
        raise ValueError(
            f"Unknown paper type: {paper_type}"
        )

    return folder / filename


# ============================================================
# DOWNLOAD
# ============================================================

def download_pdf(paper):
    destination = get_destination(paper)

    unit = paper["unit"]
    year = paper["year"]
    month = paper["month"]
    paper_type = paper["type"]
    url = paper["url"]

    label = (
        f"{unit} "
        f"{month} {year} "
        f"{paper_type}"
    )

    # --------------------------------------------------------
    # Already downloaded
    # --------------------------------------------------------

    if valid_pdf_file(destination):
        print(f"  ✓ {label} already exists")
        return "skipped"

    # Remove corrupt/partial file from an earlier failed run.
    if destination.exists():

        print(
            f"  ! Existing file is invalid. "
            f"Re-downloading {label}"
        )

        try:
            destination.unlink()
        except OSError:
            pass

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    try:

        with session.get(
            url,
            timeout=TIMEOUT,
            stream=True,
        ) as response:

            response.raise_for_status()

            content_type = (
                response.headers
                .get("Content-Type", "")
                .lower()
            )

            temp_path = destination.with_suffix(
                ".pdf.part"
            )

            with temp_path.open("wb") as f:

                for chunk in response.iter_content(
                    chunk_size=1024 * 128
                ):

                    if chunk:
                        f.write(chunk)

    except requests.RequestException as e:

        print(f"  ✗ {label}")
        print(f"    {e}")

        return "failed"

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not valid_pdf_file(temp_path):

        print(f"  ✗ {label}")
        print("    Downloaded response is not a valid PDF.")
        print(f"    URL: {url}")

        try:
            temp_path.unlink()
        except OSError:
            pass

        return "failed"

    # Atomic-ish move from .part to final file.
    temp_path.replace(destination)

    size_mb = destination.stat().st_size / (
        1024 * 1024
    )

    print(
        f"  ↓ {label} "
        f"({size_mb:.2f} MB)"
    )

    return "downloaded"


# ============================================================
# REPORT
# ============================================================

def show_discovered_sessions(papers):
    """
    Show what PMT currently contains before downloading.
    """

    sessions = {}

    for paper in papers:

        key = (
            paper["unit"],
            paper["year"],
            paper["month"],
        )

        if key not in sessions:
            sessions[key] = set()

        sessions[key].add(
            paper["type"]
        )

    print()
    print("Discovered exam sessions")
    print("-" * 60)

    for key in sorted(
        sessions,
        key=lambda x: (
            x[0],
            x[1],
            month_sort_value(x[2]),
        ),
    ):

        unit, year, month = key

        types = sessions[key]

        qp = "QP" if "QP" in types else "--"
        ms = "MS" if "MS" in types else "--"

        print(
            f"{unit:<6} "
            f"{year:<4} "
            f"{month:<8} "
            f"[{qp}] [{ms}]"
        )


# ============================================================
# CHECK FOR INCOMPLETE PAIRS
# ============================================================

def find_incomplete_sessions(papers):
    """
    Detect sessions where PMT has only a QP or only an MS.
    """

    sessions = {}

    for paper in papers:

        key = (
            paper["unit"],
            paper["year"],
            paper["month"],
        )

        sessions.setdefault(
            key,
            set(),
        ).add(
            paper["type"]
        )

    incomplete = []

    for key, types in sessions.items():

        if types != {"QP", "MS"}:

            incomplete.append(
                (
                    key,
                    types,
                )
            )

    return incomplete


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("Edexcel IAL Physics Past Paper Downloader")
    print("Auto-discovery version")
    print("=" * 60)

    print()
    print("Units:")
    print("  WPH11 - Unit 1")
    print("  WPH12 - Unit 2")

    print()
    print("Source:")
    print("  Physics & Maths Tutor")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Discover
    # --------------------------------------------------------

    all_papers = []

    for unit_code, config in UNITS.items():

        papers = discover_papers(
            unit_code,
            config,
        )

        all_papers.extend(papers)

    if not all_papers:

        print()
        print("ERROR: No papers were discovered.")
        print()
        print(
            "PMT may have changed its website structure."
        )
        print(
            "No files have been downloaded."
        )
        return

    # --------------------------------------------------------
    # Display discovery result
    # --------------------------------------------------------

    show_discovered_sessions(
        all_papers
    )

    # --------------------------------------------------------
    # Detect missing QP/MS pairs
    # --------------------------------------------------------

    incomplete = find_incomplete_sessions(
        all_papers
    )

    if incomplete:

        print()
        print("WARNING: Incomplete sessions detected:")
        print()

        for key, types in incomplete:

            unit, year, month = key

            print(
                f"  {unit} {month} {year}: "
                f"{', '.join(sorted(types))}"
            )

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("Downloading")
    print("=" * 60)
    print()

    stats = {
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
    }

    failed_papers = []

    for index, paper in enumerate(
        all_papers,
        start=1,
    ):

        print(
            f"[{index}/{len(all_papers)}]",
            end=" ",
        )

        result = download_pdf(
            paper
        )

        stats[result] += 1

        if result == "failed":
            failed_papers.append(
                paper
            )

        if result == "downloaded":
            time.sleep(
                DOWNLOAD_DELAY
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)

    print()
    print(
        f"Discovered : {len(all_papers)}"
    )

    print(
        f"Downloaded : {stats['downloaded']}"
    )

    print(
        f"Already had: {stats['skipped']}"
    )

    print(
        f"Failed     : {stats['failed']}"
    )

    print()
    print("Saved to:")
    print(f"  {OUTPUT_DIR}")

    # --------------------------------------------------------
    # Failed downloads
    # --------------------------------------------------------

    if failed_papers:

        print()
        print("Failed downloads:")
        print()

        for paper in failed_papers:

            print(
                f"  - "
                f"{paper['unit']} "
                f"{paper['month']} "
                f"{paper['year']} "
                f"{paper['type']}"
            )

            print(
                f"    {paper['url']}"
            )

    print()


if __name__ == "__main__":
    main()