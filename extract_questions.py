#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

RENDER_DPI = 180

VALID_UNITS = {"WPH11", "WPH12"}

UNIT_NAMES = {
    "WPH11": "Mechanics and Materials",
    "WPH12": "Waves and Electricity",
}

SESSION_NAMES = {
    "JAN": "January",
    "MAY_JUNE": "May/June",
    "OCT": "October",
}

# Edexcel current-spec papers normally contain numbered questions
# in roughly this range.
MIN_QUESTION = 1
MAX_QUESTION = 30


# ============================================================
# TEXT CLEANING
# ============================================================

NOISE_PATTERNS = [
    r"DO NOT WRITE IN THIS AREA",
    r"Turn over",
    r"©\s*\d{4}\s*Pearson Education Ltd\.",
    r"Pearson",
    r"PMT",
    r"\*P[A-Z0-9]+\*",
    r"",
    r"",
]


def clean_text(text):
    """
    Clean common Pearson/PMT page noise while preserving the
    actual question wording.
    """

    if not text:
        return ""

    text = text.replace("\u00ad", "")
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")

    for pattern in NOISE_PATTERNS:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    # Remove huge answer lines made from dots.
    text = re.sub(
        r"\.{20,}",
        "",
        text,
    )

    # Remove isolated page numbers.
    text = re.sub(
        r"(?m)^\s*\d{1,2}\s*$",
        "",
        text,
    )

    # Collapse repeated spaces but preserve line breaks.
    lines = []

    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line)
        line = line.strip()

        if line:
            lines.append(line)

    return "\n".join(lines).strip()


# ============================================================
# SESSION METADATA
# ============================================================

def parse_session_folder(folder_name):
    """
    2024_JAN       -> (2024, "JAN", "January")
    2023_MAY_JUNE  -> (2023, "MAY_JUNE", "May/June")
    2022_OCT       -> (2022, "OCT", "October")
    """

    match = re.match(
        r"^(\d{4})_(JAN|MAY_JUNE|OCT)$",
        folder_name,
    )

    if not match:
        return None

    year = int(match.group(1))
    session_code = match.group(2)

    return (
        year,
        session_code,
        SESSION_NAMES[session_code],
    )


# ============================================================
# PDF HELPERS
# ============================================================

def get_page_lines(page):
    """
    Return text lines with approximate coordinates.

    Each result:
        {
            "text": "...",
            "x0": ...,
            "y0": ...,
            "x1": ...,
            "y1": ...
        }
    """

    data = page.get_text(
        "dict",
        sort=True,
    )

    results = []

    for block in data.get("blocks", []):

        if block.get("type") != 0:
            continue

        for line in block.get("lines", []):

            spans = line.get("spans", [])

            if not spans:
                continue

            text = "".join(
                span.get("text", "")
                for span in spans
            ).strip()

            if not text:
                continue

            bbox = line.get("bbox")

            results.append({
                "text": text,
                "x0": bbox[0],
                "y0": bbox[1],
                "x1": bbox[2],
                "y1": bbox[3],
            })

    results.sort(
        key=lambda item: (
            item["y0"],
            item["x0"],
        )
    )

    return results


def page_text(page):
    return clean_text(
        page.get_text(
            "text",
            sort=True,
        )
    )


# ============================================================
# QUESTION END DETECTION
# ============================================================

TOTAL_PATTERN = re.compile(
    r"Total\s+for\s+Question\s+(\d+)\s*=\s*(\d+)\s*marks?",
    re.IGNORECASE,
)


def find_question_totals(doc):
    """
    Find markers such as:

        (Total for Question 14 = 9 marks)

    These are extremely useful because they give us:
      - question number
      - total marks
      - exact end location

    Returns:

        [
            {
                "question_number": 1,
                "marks": 1,
                "page": 1,
                "y": 500
            },
            ...
        ]
    """

    results = []

    for page_index, page in enumerate(doc):

        # Search line/block text first.
        blocks = page.get_text(
            "blocks",
            sort=True,
        )

        for block in blocks:

            x0, y0, x1, y1, text, *_ = block

            normalized = re.sub(
                r"\s+",
                " ",
                text,
            )

            for match in TOTAL_PATTERN.finditer(
                normalized
            ):

                number = int(match.group(1))
                marks = int(match.group(2))

                if not (
                    MIN_QUESTION
                    <= number
                    <= MAX_QUESTION
                ):
                    continue

                results.append({
                    "question_number": number,
                    "marks": marks,
                    "page": page_index,
                    "y": y1,
                })

    # Remove duplicates.
    unique = {}

    for item in results:

        number = item["question_number"]

        if number not in unique:
            unique[number] = item

    return [
        unique[number]
        for number in sorted(unique)
    ]


# ============================================================
# QUESTION START DETECTION
# ============================================================

def find_question_start_on_pages(
    doc,
    question_number,
    start_page,
    end_page,
):
    """
    Search backwards/within the question's page range for a line
    beginning with the question number.

    Example:
        "14 A child's slide..."
    """

    pattern = re.compile(
        rf"^\s*{question_number}\s+(?=\S)"
    )

    for page_index in range(
        start_page,
        end_page + 1,
    ):

        page = doc[page_index]
        lines = get_page_lines(page)

        for line in lines:

            text = line["text"]

            if pattern.match(text):

                return {
                    "page": page_index,
                    "y": max(
                        0,
                        line["y0"] - 5,
                    ),
                }

    return None


def build_question_ranges(doc):
    """
    Determine question boundaries using Pearson's
    "Total for Question N" markers.
    """

    totals = find_question_totals(doc)

    if not totals:
        return []

    ranges = []

    previous_end_page = 0
    previous_end_y = 0

    for total in totals:

        number = total["question_number"]
        end_page = total["page"]

        # The next question must start after the previous question.
        search_start_page = previous_end_page

        start = find_question_start_on_pages(
            doc,
            number,
            search_start_page,
            end_page,
        )

        if start is None:
            # Fallback.
            start = {
                "page": search_start_page,
                "y": previous_end_y,
            }

        ranges.append({
            "question_number": number,
            "marks": total["marks"],

            "start_page": start["page"],
            "start_y": start["y"],

            "end_page": end_page,
            "end_y": total["y"],
        })

        previous_end_page = end_page
        previous_end_y = total["y"]

    return ranges


# ============================================================
# EXTRACT QUESTION TEXT
# ============================================================

def extract_range_text(doc, question_range):
    """
    Extract text only from the region occupied by one question.
    """

    pieces = []

    start_page = question_range["start_page"]
    end_page = question_range["end_page"]

    for page_index in range(
        start_page,
        end_page + 1,
    ):

        page = doc[page_index]

        top = 0
        bottom = page.rect.height

        if page_index == start_page:
            top = question_range["start_y"]

        if page_index == end_page:
            bottom = question_range["end_y"]

        # Leave out extreme left/right margins and headers.
        clip = pymupdf.Rect(
            25,
            max(20, top),
            page.rect.width - 25,
            min(page.rect.height - 20, bottom),
        )

        text = page.get_text(
            "text",
            clip=clip,
            sort=True,
        )

        pieces.append(text)

    text = "\n".join(pieces)

    return clean_text(text)


# ============================================================
# QUESTION IMAGE RENDERING
# ============================================================

def render_question(
    doc,
    question_range,
    destination_dir,
    filename_prefix,
):
    """
    Render the original PDF region occupied by the question.

    Multi-page questions produce multiple PNGs.

    Example:
        WPH11_2024_JAN_Q14_p1.png
        WPH11_2024_JAN_Q14_p2.png
    """

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_files = []

    start_page = question_range["start_page"]
    end_page = question_range["end_page"]

    image_index = 1

    for page_index in range(
        start_page,
        end_page + 1,
    ):

        page = doc[page_index]

        top = 20
        bottom = page.rect.height - 20

        if page_index == start_page:
            top = max(
                20,
                question_range["start_y"] - 5,
            )

        if page_index == end_page:
            bottom = min(
                page.rect.height - 20,
                question_range["end_y"] + 5,
            )

        if bottom <= top:
            continue

        clip = pymupdf.Rect(
            20,
            top,
            page.rect.width - 20,
            bottom,
        )

        pixmap = page.get_pixmap(
            dpi=RENDER_DPI,
            clip=clip,
            alpha=False,
        )

        filename = (
            f"{filename_prefix}_"
            f"p{image_index}.png"
        )

        destination = (
            destination_dir
            / filename
        )

        pixmap.save(
            str(destination)
        )

        output_files.append(
            destination
        )

        image_index += 1

    return output_files


# ============================================================
# MARK SCHEME EXTRACTION
# ============================================================

def extract_mark_scheme_pages(ms_doc):
    """
    Convert every mark-scheme page to cleaned text.

    Mark schemes are table-heavy, so we keep this separate from
    question-paper parsing.
    """

    pages = []

    for page_index, page in enumerate(ms_doc):

        text = page_text(page)

        pages.append({
            "page": page_index,
            "text": text,
        })

    return pages


def find_mark_scheme_start(
    pages,
    question_number,
):
    """
    Find likely first page containing the mark scheme row for a
    question.

    Mark schemes differ slightly by year, so this is intentionally
    conservative.
    """

    patterns = [
        re.compile(
            rf"(?m)^\s*{question_number}\s*(?:\([a-z]\))?",
            re.IGNORECASE,
        ),

        re.compile(
            rf"(?m)^\s*Question\s+{question_number}\b",
            re.IGNORECASE,
        ),
    ]

    for item in pages:

        text = item["text"]

        for pattern in patterns:

            if pattern.search(text):
                return item["page"]

    return None


def extract_mark_scheme_for_question(
    ms_doc,
    ms_pages,
    question_number,
    next_question_number,
):
    """
    Extract an approximate mark-scheme section.

    This is intentionally stored as raw extracted MS text.
    Later we can build a more sophisticated subpart parser.
    """

    start_page = find_mark_scheme_start(
        ms_pages,
        question_number,
    )

    if start_page is None:
        return {
            "text": "",
            "pages": [],
            "matched": False,
        }

    if next_question_number is not None:

        next_start = find_mark_scheme_start(
            ms_pages,
            next_question_number,
        )

    else:
        next_start = None

    if (
        next_start is not None
        and next_start >= start_page
    ):
        end_page = next_start
    else:
        end_page = min(
            start_page + 2,
            len(ms_doc) - 1,
        )

    pieces = []

    used_pages = []

    for page_index in range(
        start_page,
        end_page + 1,
    ):

        text = page_text(
            ms_doc[page_index]
        )

        pieces.append(text)
        used_pages.append(
            page_index + 1
        )

    combined = "\n".join(pieces)

    return {
        "text": combined,
        "pages": used_pages,
        "matched": True,
    }


# ============================================================
# PROCESS ONE PAPER
# ============================================================

def process_paper(
    unit,
    session_folder,
    question_pdf,
    mark_scheme_pdf,
):
    parsed = parse_session_folder(
        session_folder.name
    )

    if parsed is None:
        return []

    year, session_code, session_name = parsed

    print()
    print("=" * 70)
    print(
        f"{unit} | {year} {session_name}"
    )
    print("=" * 70)

    print(f"QP: {question_pdf}")
    print(f"MS: {mark_scheme_pdf}")

    try:

        qp_doc = pymupdf.open(
            question_pdf
        )

    except Exception as e:

        print(
            f"ERROR opening question paper: {e}"
        )

        return []

    try:

        ms_doc = pymupdf.open(
            mark_scheme_pdf
        )

    except Exception as e:

        qp_doc.close()

        print(
            f"ERROR opening mark scheme: {e}"
        )

        return []

    ranges = build_question_ranges(
        qp_doc
    )

    if not ranges:

        print(
            "WARNING: No question boundaries found."
        )

        qp_doc.close()
        ms_doc.close()

        return []

    print(
        f"Found {len(ranges)} questions."
    )

    ms_pages = extract_mark_scheme_pages(
        ms_doc
    )

    session_output_dir = (
        OUTPUT_DIR
        / unit
        / session_folder.name
    )

    image_dir = (
        session_output_dir
        / "images"
    )

    session_output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    questions = []

    for index, question_range in enumerate(
        ranges
    ):

        number = (
            question_range[
                "question_number"
            ]
        )

        next_number = None

        if index + 1 < len(ranges):

            next_number = (
                ranges[index + 1][
                    "question_number"
                ]
            )

        question_text = extract_range_text(
            qp_doc,
            question_range,
        )

        prefix = (
            f"{unit}_"
            f"{year}_"
            f"{session_code}_"
            f"Q{number:02d}"
        )

        images = render_question(
            qp_doc,
            question_range,
            image_dir,
            prefix,
        )

        ms_result = (
            extract_mark_scheme_for_question(
                ms_doc,
                ms_pages,
                number,
                next_number,
            )
        )

        relative_images = [
            str(
                image.relative_to(
                    PROJECT_ROOT
                )
            )
            for image in images
        ]

        question = {
            "id": (
                f"{unit}-"
                f"{year}-"
                f"{session_code}-"
                f"Q{number}"
            ),

            "board": "Pearson Edexcel",

            "qualification": (
                "International Advanced "
                "Subsidiary"
            ),

            "subject": "Physics",

            "unit": unit,

            "unit_name": (
                UNIT_NAMES.get(
                    unit,
                    ""
                )
            ),

            "paper_code": (
                f"{unit}/01"
            ),

            "year": year,

            "session": session_name,

            "session_code": (
                session_code
            ),

            "question_number": (
                str(number)
            ),

            "marks": (
                question_range[
                    "marks"
                ]
            ),

            "question_text": (
                question_text
            ),

            "mark_scheme_text": (
                ms_result["text"]
            ),

            "mark_scheme_matched": (
                ms_result["matched"]
            ),

            "question_pages": list(
                range(
                    question_range[
                        "start_page"
                    ] + 1,

                    question_range[
                        "end_page"
                    ] + 2,
                )
            ),

            "mark_scheme_pages": (
                ms_result["pages"]
            ),

            "question_images": (
                relative_images
            ),

            "source_question_pdf": str(
                question_pdf.relative_to(
                    PROJECT_ROOT
                )
            ),

            "source_mark_scheme_pdf": str(
                mark_scheme_pdf.relative_to(
                    PROJECT_ROOT
                )
            ),

            # Filled by classify_questions.py later.
            "topic": None,
            "subtopic": None,
            "difficulty": None,
            "question_type": None,
            "skills": [],
            "classification_confidence": None,
        }

        questions.append(
            question
        )

        ms_status = (
            "MS ✓"
            if ms_result["matched"]
            else "MS ✗"
        )

        print(
            f"  Q{number:<2} "
            f"{question_range['marks']:>2} marks | "
            f"{len(images)} image(s) | "
            f"{ms_status}"
        )

    # ========================================================
    # SAVE SESSION JSON
    # ========================================================

    json_path = (
        session_output_dir
        / "questions.json"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            questions,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        f"Saved: {json_path}"
    )

    qp_doc.close()
    ms_doc.close()

    return questions


# ============================================================
# DISCOVER PAPERS
# ============================================================

def discover_sessions():
    """
    Walk:

        data/
        ├── WPH11/
        └── WPH12/

    and find folders containing both PDFs.
    """

    sessions = []

    for unit in sorted(
        VALID_UNITS
    ):

        unit_dir = (
            DATA_DIR
            / unit
        )

        if not unit_dir.exists():
            continue

        for session_dir in sorted(
            unit_dir.iterdir()
        ):

            if not session_dir.is_dir():
                continue

            if (
                parse_session_folder(
                    session_dir.name
                )
                is None
            ):
                continue

            qp = (
                session_dir
                / "question.pdf"
            )

            ms = (
                session_dir
                / "mark_scheme.pdf"
            )

            if not qp.exists():

                print(
                    f"Skipping {session_dir}: "
                    f"question.pdf missing"
                )

                continue

            if not ms.exists():

                print(
                    f"Skipping {session_dir}: "
                    f"mark_scheme.pdf missing"
                )

                continue

            sessions.append({
                "unit": unit,
                "directory": session_dir,
                "question_pdf": qp,
                "mark_scheme_pdf": ms,
            })

    return sessions


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Extract Edexcel IAL Physics "
            "questions from downloaded PDFs."
        )
    )

    parser.add_argument(
        "--unit",
        choices=[
            "WPH11",
            "WPH12",
        ],
        help=(
            "Only process one unit."
        ),
    )

    parser.add_argument(
        "--session",
        help=(
            "Only process one session, "
            "e.g. 2024_JAN"
        ),
    )

    args = parser.parse_args()

    print()
    print("=" * 70)
    print(
        "Edexcel IAL Physics Question Extractor"
    )
    print("=" * 70)

    sessions = discover_sessions()

    if args.unit:

        sessions = [
            item
            for item in sessions
            if item["unit"]
            == args.unit
        ]

    if args.session:

        sessions = [
            item
            for item in sessions
            if (
                item["directory"].name
                == args.session
            )
        ]

    if not sessions:

        print()
        print(
            "No matching paper sessions found."
        )

        print()
        print(
            "Expected structure:"
        )

        print(
            "data/WPH11/2024_JAN/"
            "question.pdf"
        )

        print(
            "data/WPH11/2024_JAN/"
            "mark_scheme.pdf"
        )

        sys.exit(1)

    print()
    print(
        f"Found {len(sessions)} "
        f"paper session(s)."
    )

    all_questions = []

    failed_sessions = []

    for item in sessions:

        questions = process_paper(
            unit=item["unit"],
            session_folder=(
                item["directory"]
            ),
            question_pdf=(
                item["question_pdf"]
            ),
            mark_scheme_pdf=(
                item["mark_scheme_pdf"]
            ),
        )

        if questions:

            all_questions.extend(
                questions
            )

        else:

            failed_sessions.append(
                str(item["directory"])
            )

    # ========================================================
    # MASTER JSON
    # ========================================================

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    master_path = (
        OUTPUT_DIR
        / "questions.json"
    )

    with master_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            all_questions,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)

    print()
    print(
        f"Sessions processed : "
        f"{len(sessions)}"
    )

    print(
        f"Questions extracted: "
        f"{len(all_questions)}"
    )

    print(
        f"Failed sessions     : "
        f"{len(failed_sessions)}"
    )

    print()
    print(
        f"Master database:"
    )

    print(
        f"  {master_path}"
    )

    if failed_sessions:

        print()
        print(
            "Sessions needing inspection:"
        )

        for item in failed_sessions:
            print(
                f"  - {item}"
            )

    print()


if __name__ == "__main__":
    main()