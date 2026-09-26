#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from taxonomy import TAXONOMIES


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"

INPUT_FILE = OUTPUT_DIR / "questions.json"
OUTPUT_FILE = OUTPUT_DIR / "enriched_questions.json"
STATUS_FILE = OUTPUT_DIR / "classification_status.json"

ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_MODEL = "gemini-3.8-flash"

AVAILABLE_MODELS = [
    {
        "id": "gemini-3.8-flash",
        "name": "Gemini 3.8 Flash",
        "description": "Fast and cheap. Recommended for bulk classification.",
    },
    {
        "id": "gemini-3.7-flash",
        "name": "Gemini 3.7 Flash",
        "description": "Good alternative.",
    },    
    {
        "id": "gemini-3.6-flash",
        "name": "Gemini 3.6 Flash",
        "description": "Older but capable",
    },    
    {
        "id": "gemini-3.5-flash",
        "name": "Gemini 3.5 Flash",
        "description": "Older bulk option",
    },      
    {
        "id": "gemini-3.5-flash-lite",
        "name": "Gemini 3.5 Flash Lite",
        "description": "Cheap/high-volume option",
    }, 
    {
        "id": "gemini-3.1-flash-lite",
        "name": "Gemini 3.1 Flash Lite",
        "description": "Very cost-focused",
    },   
    {
        "id": "gemini-3.8-pro",
        "name": "Gemini 3.8 Pro",
        "description": "Higher quality reasoning, but slower and more expensive.",
    },
]

REQUEST_DELAY = 1.0

# Number of retries for temporary API/network errors.
MAX_RETRIES = 20

# Questions below this confidence are still saved, but are marked
# as needing manual review.
REVIEW_CONFIDENCE_THRESHOLD = 0.75


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(ENV_FILE)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print()
    print("ERROR: GEMINI_API_KEY not found.")
    print()
    print("Expected .env file:")
    print(f"  {ENV_FILE}")
    print()
    print("Containing:")
    print("  GEMINI_API_KEY=your_api_key_here")
    print()
    sys.exit(1)


client = genai.Client(
    api_key=API_KEY
)


# ============================================================
# STRUCTURED OUTPUT
# ============================================================

class SubQuestion(BaseModel):

    id: str = Field(
        description=(
            "Subquestion identifier exactly as printed, "
            "for example 'a', 'a(i)', 'a(ii)', 'b'. "
            "Use 'main' if the question has no subparts."
        )
    )

    question_text: str = Field(
        description=(
            "Complete text required to understand this "
            "subquestion. Include essential shared stem context "
            "when necessary."
        )
    )

    marks: int | None = Field(
        default=None,
        description=(
            "Marks allocated to this specific subquestion."
        )
    )

    mark_scheme: str = Field(
        description=(
            "Only the mark-scheme content relevant to this "
            "subquestion. Preserve important equations, "
            "accepted alternatives, M/A/B marks and units."
        )
    )

    primary_topic: str = Field(
        description="Primary taxonomy category."
    )

    subtopic: str = Field(
        description=(
            "Specific subtopic chosen from the supplied taxonomy."
        )
    )

    secondary_subtopics: list[str] = Field(
        default_factory=list,
        description=(
            "Other relevant taxonomy subtopics."
        )
    )

    question_type: Literal[
        "MCQ",
        "Calculation",
        "Explanation",
        "Definition",
        "Derivation",
        "Graph",
        "Practical",
        "Experimental Design",
        "Data Analysis",
        "Show That",
        "Mixed",
    ]

    difficulty: Literal[
        "Easy",
        "Medium",
        "Hard",
    ]

    skills: list[str] = Field(
        default_factory=list,
        description=(
            "Specific skills required, such as algebra, "
            "graph interpretation, proportional reasoning, "
            "uncertainty calculation, explanation."
        )
    )

    requires_diagram: bool

    requires_shared_context: bool

    confidence: float = Field(
        ge=0,
        le=1,
        description=(
            "Confidence in the parsing, mark-scheme matching "
            "and classification."
        )
    )


class QuestionAnalysis(BaseModel):

    question_number: str

    shared_stem: str = Field(
        description=(
            "Text/context shared by multiple subquestions. "
            "Empty string if none."
        )
    )

    subquestions: list[SubQuestion]

    total_marks_detected: int | None

    parsing_notes: str = Field(
        description=(
            "Short note describing ambiguities or extraction "
            "problems. Empty string if none."
        )
    )


# ============================================================
# GENERAL HELPERS
# ============================================================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def safe_error_text(error):
    """
    Prevent enormous API errors from bloating the status file.
    """

    text = str(error)

    if len(text) > 2000:
        text = text[:2000] + "..."

    return text


# ============================================================
# TAXONOMY PROMPT
# ============================================================

def taxonomy_to_text(unit):

    taxonomy = TAXONOMIES[unit]

    lines = []

    for category, subtopics in taxonomy.items():

        lines.append(category)

        for subtopic in subtopics:

            lines.append(
                f"  - {subtopic}"
            )

    return "\n".join(lines)


# ============================================================
# PROMPT
# ============================================================

def build_prompt(question):

    taxonomy = taxonomy_to_text(
        question["unit"]
    )

    return f"""
You are parsing and classifying a Pearson Edexcel International
AS Physics past-paper question.

Your job is NOT to solve the question from scratch.

You are given:

1. Extracted question text
2. Extracted mark-scheme text
3. One or more images of the ORIGINAL question

The images are authoritative for visual information, equations,
graphs, tables, diagrams, mathematical notation and question
structure.

The extracted text may contain PDF extraction errors.

------------------------------------------------------------
PAPER
------------------------------------------------------------

Unit:
{question["unit"]}

Unit name:
{question["unit_name"]}

Year:
{question["year"]}

Session:
{question["session"]}

Question:
{question["question_number"]}

Expected total marks:
{question["marks"]}

------------------------------------------------------------
EXTRACTED QUESTION TEXT
------------------------------------------------------------

{question["question_text"]}

------------------------------------------------------------
EXTRACTED MARK SCHEME
------------------------------------------------------------

{question["mark_scheme_text"]}

------------------------------------------------------------
ALLOWED TAXONOMY
------------------------------------------------------------

{taxonomy}

------------------------------------------------------------
INSTRUCTIONS
------------------------------------------------------------

1. Determine the exact logical subquestion structure.

Examples:

main

a
b

a(i)
a(ii)
b(i)
b(ii)

Do not invent subquestions.

2. If there is a shared scenario, experiment, diagram, table or
introductory stem, place it in shared_stem.

3. For each subquestion, produce question_text that can be
understood when displayed in the app.

If a subquestion depends on shared context, set:

requires_shared_context = true

4. Match each subquestion to ONLY its corresponding mark-scheme
content.

Do not assign another subquestion's marking points.

5. Do not invent mark-scheme content.

If the supplied mark scheme does not clearly contain the answer,
use an empty string and reduce confidence.

6. Select primary_topic and subtopic ONLY from the taxonomy
provided above.

primary_topic must be one of the taxonomy headings.

subtopic must be one of the listed subtopics under that taxonomy.

7. secondary_subtopics must also contain ONLY values from the
provided taxonomy.

8. Difficulty means difficulty for a typical Edexcel IAS Physics
student:

Easy:
direct recall, substitution, or one-step reasoning.

Medium:
multiple steps, interpretation, standard application, or a
short explanation requiring physics reasoning.

Hard:
non-obvious modelling, synthesis of concepts, difficult
experimental reasoning, unfamiliar context, or extended
multi-step reasoning.

9. question_type describes what the STUDENT is being asked to do.

10. marks should refer to the individual subquestion.

11. The sum of subquestion marks should normally equal:

{question["marks"]}

If you cannot determine individual marks reliably, use null rather
than guessing.

12. Use the original question images to correct extraction errors.

13. Do not rewrite equations into incorrect plain-English
approximations.

14. confidence measures confidence in ALL of:
- subquestion parsing
- mark-scheme matching
- topic classification

15. Return only information supported by the provided question
and mark scheme.
""".strip()


# ============================================================
# IMAGE INPUT
# ============================================================

def load_image_parts(question):

    parts = []

    for relative_path in question.get(
        "question_images",
        [],
    ):

        image_path = (
            PROJECT_ROOT
            / relative_path
        )

        if not image_path.exists():

            print(
                f"    WARNING: Image missing: "
                f"{image_path}"
            )

            continue

        data = image_path.read_bytes()

        suffix = (
            image_path
            .suffix
            .lower()
        )

        if suffix == ".png":
            mime_type = "image/png"

        elif suffix in {
            ".jpg",
            ".jpeg",
        }:
            mime_type = "image/jpeg"

        else:

            print(
                f"    WARNING: Unsupported image: "
                f"{image_path}"
            )

            continue

        parts.append(
            types.Part.from_bytes(
                data=data,
                mime_type=mime_type,
            )
        )

    return parts


# ============================================================
# GEMINI REQUEST
# ============================================================

def analyze_question(question, model):

    prompt = build_prompt(
        question
    )

    image_parts = load_image_parts(
        question
    )

    contents = []

    # Original images first.
    contents.extend(
        image_parts
    )

    contents.append(
        prompt
    )

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            response = (
                client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type=(
                            "application/json"
                        ),
                        response_schema=(
                            QuestionAnalysis
                        ),
                        temperature=0.1,
                    ),
                )
            )

            if response.parsed:

                if isinstance(
                    response.parsed,
                    QuestionAnalysis,
                ):
                    return response.parsed

                return (
                    QuestionAnalysis
                    .model_validate(
                        response.parsed
                    )
                )

            if not response.text:

                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return (
                QuestionAnalysis
                .model_validate_json(
                    response.text
                )
            )

        except Exception as e:

            last_error = e

            print()
            print(
                f"    Attempt "
                f"{attempt}/{MAX_RETRIES} "
                f"failed:"
            )

            print(
                f"    {safe_error_text(e)}"
            )

            if attempt < MAX_RETRIES:

                wait = 2 ** attempt

                print(
                    f"    Waiting {wait}s..."
                )

                time.sleep(wait)

    raise RuntimeError(
        f"Gemini failed after "
        f"{MAX_RETRIES} attempts: "
        f"{safe_error_text(last_error)}"
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_analysis(
    original,
    analysis,
):

    warnings = []

    if not analysis.subquestions:

        warnings.append(
            "Gemini returned zero subquestions."
        )

        return warnings

    # --------------------------------------------------------
    # Question number
    # --------------------------------------------------------

    expected_number = str(
        original["question_number"]
    )

    detected_number = str(
        analysis.question_number
    )

    if detected_number != expected_number:

        warnings.append(
            f"Gemini returned question number "
            f"{detected_number}, expected "
            f"{expected_number}."
        )

    # --------------------------------------------------------
    # Marks
    # --------------------------------------------------------

    expected_marks = (
        original.get("marks")
    )

    known_marks = [
        item.marks
        for item
        in analysis.subquestions
        if item.marks is not None
    ]

    if (
        expected_marks is not None
        and len(known_marks)
        == len(analysis.subquestions)
    ):

        detected = sum(
            known_marks
        )

        if detected != expected_marks:

            warnings.append(
                f"Subquestion marks sum "
                f"to {detected}, expected "
                f"{expected_marks}."
            )

    # --------------------------------------------------------
    # Taxonomy
    # --------------------------------------------------------

    taxonomy = TAXONOMIES[
        original["unit"]
    ]

    all_valid_subtopics = {
        subtopic
        for subtopics in taxonomy.values()
        for subtopic in subtopics
    }

    for sub in analysis.subquestions:

        if (
            sub.primary_topic
            not in taxonomy
        ):

            warnings.append(
                f"{sub.id}: invalid "
                f"primary topic "
                f"'{sub.primary_topic}'."
            )

        else:

            allowed = taxonomy[
                sub.primary_topic
            ]

            if sub.subtopic not in allowed:

                warnings.append(
                    f"{sub.id}: subtopic "
                    f"'{sub.subtopic}' does not "
                    f"belong to "
                    f"'{sub.primary_topic}'."
                )

        for secondary in (
            sub.secondary_subtopics
        ):

            if (
                secondary
                not in all_valid_subtopics
            ):

                warnings.append(
                    f"{sub.id}: invalid secondary "
                    f"subtopic '{secondary}'."
                )

    # --------------------------------------------------------
    # Duplicate subquestion IDs
    # --------------------------------------------------------

    ids = [
        sub.id
        for sub
        in analysis.subquestions
    ]

    if len(ids) != len(set(ids)):

        warnings.append(
            "Duplicate subquestion IDs detected."
        )

    return warnings


# ============================================================
# REVIEW STATUS
# ============================================================

def determine_review_status(
    analysis,
    warnings,
):

    confidences = [
        sub.confidence
        for sub
        in analysis.subquestions
    ]

    if confidences:
        minimum_confidence = min(
            confidences
        )
    else:
        minimum_confidence = 0.0

    if (
        warnings
        or minimum_confidence
        < REVIEW_CONFIDENCE_THRESHOLD
    ):
        return (
            "needs_review",
            minimum_confidence,
        )

    return (
        "completed",
        minimum_confidence,
    )


# ============================================================
# CONVERT TO DATABASE RECORDS
# ============================================================

def make_subquestion_records(
    original,
    analysis,
    warnings,
    model,
):

    records = []

    review_status, minimum_confidence = (
        determine_review_status(
            analysis,
            warnings,
        )
    )

    for sub in analysis.subquestions:

        sub_id = sub.id

        if sub_id == "main":

            full_id = original["id"]

        else:

            normalized = (
                sub_id
                .replace("(", "")
                .replace(")", "")
                .replace(" ", "")
            )

            full_id = (
                f"{original['id']}-"
                f"{normalized}"
            )

        record = {

            # --------------------------------------------
            # Identity
            # --------------------------------------------

            "id": full_id,

            "parent_question_id": (
                original["id"]
            ),

            "question_number": (
                original[
                    "question_number"
                ]
            ),

            "subquestion": sub.id,

            # --------------------------------------------
            # Exam metadata
            # --------------------------------------------

            "board": (
                original["board"]
            ),

            "qualification": (
                original[
                    "qualification"
                ]
            ),

            "subject": (
                original["subject"]
            ),

            "unit": (
                original["unit"]
            ),

            "unit_name": (
                original[
                    "unit_name"
                ]
            ),

            "paper_code": (
                original[
                    "paper_code"
                ]
            ),

            "year": (
                original["year"]
            ),

            "session": (
                original[
                    "session"
                ]
            ),

            "session_code": (
                original[
                    "session_code"
                ]
            ),

            # --------------------------------------------
            # Question
            # --------------------------------------------

            "shared_stem": (
                analysis.shared_stem
            ),

            "question_text": (
                sub.question_text
            ),

            "marks": (
                sub.marks
            ),

            # --------------------------------------------
            # Mark scheme
            # --------------------------------------------

            "mark_scheme": (
                sub.mark_scheme
            ),

            # --------------------------------------------
            # Classification
            # --------------------------------------------

            "topic": (
                sub.primary_topic
            ),

            "subtopic": (
                sub.subtopic
            ),

            "secondary_subtopics": (
                sub.secondary_subtopics
            ),

            "difficulty": (
                sub.difficulty
            ),

            "question_type": (
                sub.question_type
            ),

            "skills": (
                sub.skills
            ),

            # --------------------------------------------
            # Context
            # --------------------------------------------

            "requires_diagram": (
                sub.requires_diagram
            ),

            "requires_shared_context": (
                sub.requires_shared_context
            ),

            # --------------------------------------------
            # AI metadata
            # --------------------------------------------

            "classification_confidence": (
                sub.confidence
            ),

            "minimum_parent_confidence": (
                minimum_confidence
            ),

            "review_status": (
                review_status
            ),

            "validation_warnings": (
                warnings
            ),

            "parsing_notes": (
                analysis.parsing_notes
            ),

            "model": model,

            "classified_at": utc_now(),

            # --------------------------------------------
            # Original assets
            # --------------------------------------------

            "question_images": (
                original.get(
                    "question_images",
                    [],
                )
            ),

            "question_pages": (
                original.get(
                    "question_pages",
                    [],
                )
            ),

            "mark_scheme_pages": (
                original.get(
                    "mark_scheme_pages",
                    [],
                )
            ),

            "source_question_pdf": (
                original.get(
                    "source_question_pdf"
                )
            ),

            "source_mark_scheme_pdf": (
                original.get(
                    "source_mark_scheme_pdf"
                )
            ),
        }

        records.append(
            record
        )

    return records


# ============================================================
# ATOMIC JSON SAVE
# ============================================================

def save_json(
    path,
    data,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = Path(
        str(path) + ".tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

        # Force Python's buffer to disk before replacement.
        f.flush()
        os.fsync(
            f.fileno()
        )

    temp_path.replace(
        path
    )


# ============================================================
# LOAD JSON SAFELY
# ============================================================

def load_json_file(
    path,
    default=None,
):

    if not path.exists():

        if default is not None:
            return default

        raise FileNotFoundError(
            str(path)
        )

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)

    except Exception as e:

        print()
        print(
            f"ERROR: Could not read JSON file:"
        )

        print(
            f"  {path}"
        )

        print()
        print(
            f"Reason: {e}"
        )

        print()
        print(
            "Stopping to protect existing data."
        )

        sys.exit(1)


# ============================================================
# STATUS FILE
# ============================================================

def load_status():

    if not STATUS_FILE.exists():
        return {}

    data = load_json_file(
        STATUS_FILE,
        default={},
    )

    # Backward-compatible guard.
    if not isinstance(data, dict):
        return {}

    return data


def save_status(status):

    save_json(
        STATUS_FILE,
        status,
    )


def update_status(
    status,
    parent_id,
    state,
    *,
    attempts=None,
    error=None,
    warnings=None,
    subquestion_count=None,
    minimum_confidence=None,
):

    previous = status.get(
        parent_id,
        {},
    )

    entry = {
        **previous,

        "parent_question_id": (
            parent_id
        ),

        "state": state,

        "updated_at": utc_now(),
    }

    if attempts is not None:
        entry["attempts"] = attempts

    if error is not None:
        entry["last_error"] = error

    if warnings is not None:
        entry["warnings"] = warnings

    if subquestion_count is not None:
        entry[
            "subquestion_count"
        ] = subquestion_count

    if minimum_confidence is not None:
        entry[
            "minimum_confidence"
        ] = minimum_confidence

    status[parent_id] = entry

    save_status(
        status
    )


# ============================================================
# EXISTING RECORD HELPERS
# ============================================================

def get_completed_parents(
    existing_records,
):
    """
    The enriched output is the ultimate source of truth.

    If a question has successfully saved subquestion records,
    it is complete enough to skip on future runs.
    """

    return {
        item.get(
            "parent_question_id"
        )
        for item
        in existing_records
        if item.get(
            "parent_question_id"
        )
    }


def remove_parent_records(
    records,
    parent_id,
):

    return [
        item
        for item
        in records
        if (
            item.get(
                "parent_question_id"
            )
            != parent_id
        )
    ]


# ============================================================
# PRINT RECORD SUMMARY
# ============================================================

def print_analysis_summary(
    records,
    warnings,
):

    print(
        f"    {len(records)} "
        f"subquestion(s)"
    )

    for record in records:

        confidence = (
            record[
                "classification_confidence"
            ]
        )

        print(
            f"      "
            f"{record['subquestion']:<8} "
            f"{str(record['marks']):<4} "
            f"{record['topic']} -> "
            f"{record['subtopic']} "
            f"[{record['difficulty']}] "
            f"conf={confidence:.2f}"
        )

    if warnings:

        print(
            "    WARNINGS:"
        )

        for warning in warnings:

            print(
                f"      - {warning}"
            )


# ============================================================
# FILTER QUESTIONS
# ============================================================

def filter_questions(
    questions,
    args,
):

    if args.unit:

        questions = [
            q
            for q
            in questions
            if q["unit"]
            == args.unit
        ]

    if args.year:

        questions = [
            q
            for q
            in questions
            if q["year"]
            == args.year
        ]

    if args.session:

        questions = [
            q
            for q
            in questions
            if (
                q["session_code"]
                == args.session
            )
        ]

    if args.question:

        questions = [
            q
            for q
            in questions
            if (
                str(
                    q["question_number"]
                )
                == str(
                    args.question
                )
            )
        ]

    return questions


# ============================================================
# MODEL SELECTION
# ============================================================

def select_model():

    print()
    print("=" * 72)
    print("SELECT GEMINI MODEL")
    print("=" * 72)
    print()

    for index, model in enumerate(
        AVAILABLE_MODELS,
        start=1,
    ):

        print(
            f"  [{index}] {model['name']}"
        )

        print(
            f"      {model['id']}"
        )

        print(
            f"      {model['description']}"
        )

        print()

    while True:

        try:

            choice = input(
                f"Select model "
                f"[1-{len(AVAILABLE_MODELS)}]: "
            ).strip()

        except KeyboardInterrupt:

            print()
            print()
            print("Cancelled.")
            sys.exit(0)

        if not choice:

            print(
                "Please select a model."
            )

            continue

        try:

            number = int(choice)

        except ValueError:

            print(
                "Please enter a number."
            )

            continue

        if (
            number < 1
            or number > len(AVAILABLE_MODELS)
        ):

            print(
                f"Please enter a number "
                f"between 1 and "
                f"{len(AVAILABLE_MODELS)}."
            )

            continue

        selected = (
            AVAILABLE_MODELS[
                number - 1
            ]
        )

        print()
        print(
            f"Selected: "
            f"{selected['name']}"
        )

        print(
            f"Model ID: "
            f"{selected['id']}"
        )

        print()

        return selected["id"]

# ============================================================
# ARGUMENTS
# ============================================================

def parse_arguments():

    parser = argparse.ArgumentParser(
        description=(
            "Split, classify and match "
            "Edexcel IAS Physics questions "
            "using Gemini."
        )
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Gemini model ID. "
            "If omitted, an interactive "
            "model selector is shown."
        ),
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
        "--year",
        type=int,
        help=(
            "Only process one year."
        ),
    )

    parser.add_argument(
        "--session",
        choices=[
            "JAN",
            "MAY_JUNE",
            "OCT",
        ],
        help=(
            "Only process one exam session."
        ),
    )

    parser.add_argument(
        "--question",
        type=str,
        help=(
            "Only process one parent "
            "question number, e.g. 14."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Reprocess matching questions "
            "even if already completed."
        ),
    )

    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help=(
            "Only process questions whose "
            "status is failed, while still "
            "respecting saved completed records."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Process at most N new questions "
            "during this run."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_arguments()

    # ========================================================
    # MODEL SELECTION
    # ========================================================

    if args.model:

        selected_model = (
            args.model.strip()
        )

        print()
        print(
            f"Using model from command line:"
        )

        print(
            f"  {selected_model}"
        )

        print()

    else:

        selected_model = (
            select_model()
        )

    # --------------------------------------------------------
    # Load source questions
    # --------------------------------------------------------

    if not INPUT_FILE.exists():

        print()
        print(
            f"ERROR: {INPUT_FILE} "
            f"does not exist."
        )

        print()
        print(
            "Run extract_questions.py first."
        )

        sys.exit(1)

    questions = load_json_file(
        INPUT_FILE
    )

    if not isinstance(
        questions,
        list,
    ):

        print()
        print(
            "ERROR: questions.json must "
            "contain a JSON list."
        )

        sys.exit(1)

    questions = filter_questions(
        questions,
        args,
    )

    if not questions:

        print()
        print(
            "No matching questions."
        )

        return

    # --------------------------------------------------------
    # Load previous successful output
    # --------------------------------------------------------

    existing_records = []

    if OUTPUT_FILE.exists():

        existing_records = (
            load_json_file(
                OUTPUT_FILE,
                default=[],
            )
        )

        if not isinstance(
            existing_records,
            list,
        ):

            print()
            print(
                "ERROR: enriched_questions.json "
                "must contain a JSON list."
            )

            sys.exit(1)

    # --------------------------------------------------------
    # Load checkpoint/status data
    # --------------------------------------------------------

    status = load_status()

    completed_parents = (
        get_completed_parents(
            existing_records
        )
    )

    # --------------------------------------------------------
    # retry-failed filter
    # --------------------------------------------------------

    if args.retry_failed:

        failed_ids = {
            parent_id
            for parent_id, item
            in status.items()
            if (
                item.get("state")
                == "failed"
            )
        }

        questions = [
            question
            for question
            in questions
            if question["id"]
            in failed_ids
        ]

        if not questions:

            print()
            print(
                "No failed questions "
                "to retry."
            )

            return

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print(
        "Edexcel Physics AI "
        "Question Enrichment"
    )
    print("=" * 72)

    print()
    print(
        f"Model              : {selected_model}"
    )

    print(
        f"Questions selected : "
        f"{len(questions)}"
    )

    print(
        f"Stored subquestions: "
        f"{len(existing_records)}"
    )

    print(
        f"Completed parents  : "
        f"{len(completed_parents)}"
    )

    print(
        f"Checkpoint entries : "
        f"{len(status)}"
    )

    if args.force:

        print(
            "Mode               : FORCE"
        )

    elif args.retry_failed:

        print(
            "Mode               : "
            "RETRY FAILED"
        )

    else:

        print(
            "Mode               : RESUME"
        )

    if args.limit:

        print(
            f"Run limit          : "
            f"{args.limit}"
        )

    print()

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    processed_this_run = 0
    skipped_this_run = 0
    failed_this_run = 0
    review_this_run = 0

    # Number of Gemini questions actually attempted.
    attempted_this_run = 0

    # --------------------------------------------------------
    # Process
    # --------------------------------------------------------

    for index, question in enumerate(
        questions,
        start=1,
    ):

        parent_id = question["id"]

        print(
            f"[{index}/{len(questions)}] "
            f"{parent_id}"
        )

        # ====================================================
        # SKIP SUCCESSFULLY SAVED QUESTIONS
        # ====================================================

        if (
            parent_id
            in completed_parents
            and not args.force
        ):

            print(
                "    ✓ Already completed. "
                "Skipping."
            )

            skipped_this_run += 1

            continue

        # ====================================================
        # LIMIT
        # ====================================================

        if (
            args.limit is not None
            and attempted_this_run
            >= args.limit
        ):

            print()
            print(
                f"Run limit of "
                f"{args.limit} reached."
            )

            break

        attempted_this_run += 1

        # ====================================================
        # ATTEMPT COUNT
        # ====================================================

        previous_status = (
            status.get(
                parent_id,
                {},
            )
        )

        attempt_count = (
            previous_status.get(
                "attempts",
                0,
            )
            + 1
        )

        update_status(
            status,
            parent_id,
            "processing",
            attempts=attempt_count,
            error=None,
        )

        # ====================================================
        # GEMINI
        # ====================================================

        try:

            analysis = analyze_question(
                question,
                selected_model,
            )

            # --------------------------------------------
            # Empty analysis protection
            # --------------------------------------------

            if not analysis.subquestions:

                raise RuntimeError(
                    "Gemini returned zero "
                    "subquestions."
                )

            # --------------------------------------------
            # Validate
            # --------------------------------------------

            warnings = (
                validate_analysis(
                    question,
                    analysis,
                )
            )

            # --------------------------------------------
            # Convert
            # --------------------------------------------

            records = (
                make_subquestion_records(
                    question,
                    analysis,
                    warnings,
                    selected_model,
                )
            )

            if not records:

                raise RuntimeError(
                    "No database records were "
                    "created from Gemini output."
                )

            # --------------------------------------------
            # Print
            # --------------------------------------------

            print_analysis_summary(
                records,
                warnings,
            )

            review_status, minimum_confidence = (
                determine_review_status(
                    analysis,
                    warnings,
                )
            )

            # =================================================
            # COMMIT RESULT
            # =================================================
            #
            # This is the important resume logic.
            #
            # We build the new complete output first.
            # The old records are untouched until save_json()
            # atomically replaces the file.
            #
            # If --force is being used, old records for this
            # parent are removed before inserting the new ones.
            # =================================================

            updated_records = (
                remove_parent_records(
                    existing_records,
                    parent_id,
                )
            )

            updated_records.extend(
                records
            )

            # -------------------------------------------------
            # SAVE SUCCESSFUL QUESTION IMMEDIATELY
            # -------------------------------------------------

            save_json(
                OUTPUT_FILE,
                updated_records,
            )

            # Only update our in-memory copy AFTER disk save
            # succeeds.
            existing_records = (
                updated_records
            )

            # Only mark as completed AFTER output was safely
            # written.
            completed_parents.add(
                parent_id
            )

            # -------------------------------------------------
            # Status
            # -------------------------------------------------

            if (
                review_status
                == "needs_review"
            ):

                state = "needs_review"

                review_this_run += 1

            else:

                state = "completed"

            update_status(
                status,
                parent_id,
                state,
                attempts=attempt_count,
                error=None,
                warnings=warnings,
                subquestion_count=(
                    len(records)
                ),
                minimum_confidence=(
                    minimum_confidence
                ),
            )

            processed_this_run += 1

            print(
                "    ✓ Saved successfully"
            )

            if state == "needs_review":

                print(
                    "    ! Flagged for "
                    "manual review"
                )

        # ====================================================
        # FAILURE
        # ====================================================

        except KeyboardInterrupt:

            print()
            print()
            print(
                "Interrupted by user."
            )

            print(
                "Previously completed questions "
                "are safely stored."
            )

            print(
                "Run the script again to resume."
            )

            break

        except Exception as e:

            failed_this_run += 1

            error_text = (
                safe_error_text(e)
            )

            print()
            print(
                "    ✗ FAILED"
            )

            print(
                f"    {error_text}"
            )

            print()
            print(
                "    Nothing was saved for "
                "this question."
            )

            print(
                "    It will be retried "
                "next time."
            )

            # IMPORTANT:
            # Do not add parent_id to completed_parents.

            update_status(
                status,
                parent_id,
                "failed",
                attempts=attempt_count,
                error=error_text,
            )

        # ====================================================
        # REQUEST DELAY
        # ====================================================

        time.sleep(
            REQUEST_DELAY
        )

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("RUN COMPLETE")
    print("=" * 72)

    print()

    print(
        f"Processed this run : "
        f"{processed_this_run}"
    )

    print(
        f"Skipped completed  : "
        f"{skipped_this_run}"
    )

    print(
        f"Needs review       : "
        f"{review_this_run}"
    )

    print(
        f"Failed             : "
        f"{failed_this_run}"
    )

    print()

    print(
        f"Total stored "
        f"subquestions: "
        f"{len(existing_records)}"
    )

    print(
        f"Completed parent "
        f"questions: "
        f"{len(completed_parents)}"
    )

    print()

    print(
        "Output:"
    )

    print(
        f"  {OUTPUT_FILE}"
    )

    print()

    print(
        "Status/checkpoint:"
    )

    print(
        f"  {STATUS_FILE}"
    )

    print()

    if failed_this_run:

        print(
            "Retry failed questions with:"
        )

        print()

        print(
            "  python classify_questions.py "
            "--retry-failed"
        )

        print()


if __name__ == "__main__":
    main()