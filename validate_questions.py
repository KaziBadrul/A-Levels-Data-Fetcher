#!/usr/bin/env python3

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from taxonomy import TAXONOMIES


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"

SOURCE_FILE = OUTPUT_DIR / "questions.json"
ENRICHED_FILE = OUTPUT_DIR / "enriched_questions.json"

REPORT_FILE = OUTPUT_DIR / "validation_report.json"

DEFAULT_CONFIDENCE_THRESHOLD = 0.75


# ============================================================
# SEVERITY
# ============================================================

ERROR = "error"
WARNING = "warning"
INFO = "info"


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):

    if not path.exists():

        print()
        print(f"ERROR: File not found:")
        print(f"  {path}")
        print()

        sys.exit(1)

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)

    except json.JSONDecodeError as e:

        print()
        print(f"ERROR: Invalid JSON:")
        print(f"  {path}")
        print()
        print(e)
        print()

        sys.exit(1)

    except Exception as e:

        print()
        print(f"ERROR reading:")
        print(f"  {path}")
        print()
        print(e)
        print()

        sys.exit(1)


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

    temp_path.replace(
        path
    )


# ============================================================
# ISSUE CREATION
# ============================================================

def make_issue(
    severity,
    code,
    message,
    *,
    parent_id=None,
    record_id=None,
    subquestion=None,
):

    return {
        "severity": severity,
        "code": code,
        "message": message,
        "parent_question_id": parent_id,
        "record_id": record_id,
        "subquestion": subquestion,
    }


# ============================================================
# BASIC HELPERS
# ============================================================

def is_blank(value):

    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    return False


def normalize_question_number(value):

    if value is None:
        return None

    return str(value).strip()


def resolve_project_path(path_value):

    if not path_value:
        return None

    path = Path(path_value)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def build_source_map(source_questions):

    result = {}

    for question in source_questions:

        question_id = question.get("id")

        if question_id:
            result[question_id] = question

    return result


def group_by_parent(records):

    grouped = defaultdict(list)

    for record in records:

        parent_id = record.get(
            "parent_question_id"
        )

        if parent_id:
            grouped[parent_id].append(
                record
            )

    return grouped


# ============================================================
# VALID VALUES
# ============================================================

VALID_DIFFICULTIES = {
    "Easy",
    "Medium",
    "Hard",
}


VALID_QUESTION_TYPES = {
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
}


VALID_REVIEW_STATUSES = {
    "completed",
    "needs_review",
}


# ============================================================
# DATASET-LEVEL VALIDATION
# ============================================================

def validate_dataset_structure(
    source_questions,
    enriched_records,
):

    issues = []

    if not isinstance(
        source_questions,
        list,
    ):

        issues.append(
            make_issue(
                ERROR,
                "SOURCE_NOT_LIST",
                (
                    "questions.json must "
                    "contain a JSON list."
                ),
            )
        )

        return issues

    if not isinstance(
        enriched_records,
        list,
    ):

        issues.append(
            make_issue(
                ERROR,
                "ENRICHED_NOT_LIST",
                (
                    "enriched_questions.json "
                    "must contain a JSON list."
                ),
            )
        )

    return issues


# ============================================================
# DUPLICATE VALIDATION
# ============================================================

def validate_duplicate_ids(
    enriched_records,
):

    issues = []

    ids = [
        record.get("id")
        for record
        in enriched_records
        if record.get("id")
    ]

    counts = Counter(ids)

    for record_id, count in counts.items():

        if count > 1:

            issues.append(
                make_issue(
                    ERROR,
                    "DUPLICATE_RECORD_ID",
                    (
                        f"Record ID appears "
                        f"{count} times."
                    ),
                    record_id=record_id,
                )
            )

    return issues


# ============================================================
# INDIVIDUAL RECORD VALIDATION
# ============================================================

def validate_record(
    record,
    source_map,
    confidence_threshold,
):

    issues = []

    record_id = record.get("id")

    parent_id = record.get(
        "parent_question_id"
    )

    subquestion = record.get(
        "subquestion"
    )

    # --------------------------------------------------------
    # Identity
    # --------------------------------------------------------

    if is_blank(record_id):

        issues.append(
            make_issue(
                ERROR,
                "MISSING_ID",
                "Record has no ID.",
                parent_id=parent_id,
                subquestion=subquestion,
            )
        )

    if is_blank(parent_id):

        issues.append(
            make_issue(
                ERROR,
                "MISSING_PARENT_ID",
                (
                    "Record has no "
                    "parent_question_id."
                ),
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    elif parent_id not in source_map:

        issues.append(
            make_issue(
                ERROR,
                "UNKNOWN_PARENT",
                (
                    "Parent question does not "
                    "exist in questions.json."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    if is_blank(subquestion):

        issues.append(
            make_issue(
                ERROR,
                "MISSING_SUBQUESTION",
                (
                    "Subquestion identifier "
                    "is missing."
                ),
                parent_id=parent_id,
                record_id=record_id,
            )
        )

    # --------------------------------------------------------
    # Question text
    # --------------------------------------------------------

    if is_blank(
        record.get("question_text")
    ):

        issues.append(
            make_issue(
                ERROR,
                "EMPTY_QUESTION_TEXT",
                "Question text is empty.",
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Mark scheme
    # --------------------------------------------------------

    if is_blank(
        record.get("mark_scheme")
    ):

        issues.append(
            make_issue(
                WARNING,
                "EMPTY_MARK_SCHEME",
                (
                    "Mark scheme is empty "
                    "or could not be matched."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Marks
    # --------------------------------------------------------

    marks = record.get("marks")

    if marks is None:

        issues.append(
            make_issue(
                WARNING,
                "MISSING_MARKS",
                (
                    "Subquestion marks "
                    "are unknown."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    elif (
        not isinstance(marks, int)
        or isinstance(marks, bool)
    ):

        issues.append(
            make_issue(
                ERROR,
                "INVALID_MARKS_TYPE",
                (
                    f"Marks must be an "
                    f"integer or null, got "
                    f"{repr(marks)}."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    elif marks <= 0:

        issues.append(
            make_issue(
                ERROR,
                "INVALID_MARKS_VALUE",
                (
                    f"Marks must be positive, "
                    f"got {marks}."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Unit
    # --------------------------------------------------------

    unit = record.get("unit")

    if unit not in TAXONOMIES:

        issues.append(
            make_issue(
                ERROR,
                "INVALID_UNIT",
                (
                    f"Unknown unit "
                    f"'{unit}'."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

        # Cannot safely validate taxonomy.
        taxonomy = None

    else:

        taxonomy = TAXONOMIES[unit]

    # --------------------------------------------------------
    # Taxonomy
    # --------------------------------------------------------

    topic = record.get("topic")
    subtopic = record.get("subtopic")

    if taxonomy is not None:

        if topic not in taxonomy:

            issues.append(
                make_issue(
                    ERROR,
                    "INVALID_TOPIC",
                    (
                        f"Topic '{topic}' is "
                        f"not valid for {unit}."
                    ),
                    parent_id=parent_id,
                    record_id=record_id,
                    subquestion=subquestion,
                )
            )

        else:

            allowed_subtopics = taxonomy[
                topic
            ]

            if (
                subtopic
                not in allowed_subtopics
            ):

                issues.append(
                    make_issue(
                        ERROR,
                        "INVALID_SUBTOPIC",
                        (
                            f"Subtopic "
                            f"'{subtopic}' does "
                            f"not belong to "
                            f"'{topic}'."
                        ),
                        parent_id=parent_id,
                        record_id=record_id,
                        subquestion=subquestion,
                    )
                )

        all_subtopics = {
            item
            for items
            in taxonomy.values()
            for item
            in items
        }

        secondary = record.get(
            "secondary_subtopics",
            [],
        )

        if secondary is None:
            secondary = []

        if not isinstance(
            secondary,
            list,
        ):

            issues.append(
                make_issue(
                    ERROR,
                    "INVALID_SECONDARY_SUBTOPICS",
                    (
                        "secondary_subtopics "
                        "must be a list."
                    ),
                    parent_id=parent_id,
                    record_id=record_id,
                    subquestion=subquestion,
                )
            )

        else:

            for item in secondary:

                if (
                    item
                    not in all_subtopics
                ):

                    issues.append(
                        make_issue(
                            WARNING,
                            "INVALID_SECONDARY_SUBTOPIC",
                            (
                                f"Unknown secondary "
                                f"subtopic '{item}'."
                            ),
                            parent_id=parent_id,
                            record_id=record_id,
                            subquestion=subquestion,
                        )
                    )

    # --------------------------------------------------------
    # Difficulty
    # --------------------------------------------------------

    difficulty = record.get(
        "difficulty"
    )

    if (
        difficulty
        not in VALID_DIFFICULTIES
    ):

        issues.append(
            make_issue(
                ERROR,
                "INVALID_DIFFICULTY",
                (
                    f"Invalid difficulty "
                    f"'{difficulty}'."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Question type
    # --------------------------------------------------------

    question_type = record.get(
        "question_type"
    )

    if (
        question_type
        not in VALID_QUESTION_TYPES
    ):

        issues.append(
            make_issue(
                ERROR,
                "INVALID_QUESTION_TYPE",
                (
                    f"Invalid question type "
                    f"'{question_type}'."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    confidence = record.get(
        "classification_confidence"
    )

    if confidence is None:

        issues.append(
            make_issue(
                WARNING,
                "MISSING_CONFIDENCE",
                (
                    "Classification confidence "
                    "is missing."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    elif (
        not isinstance(
            confidence,
            (int, float),
        )
        or isinstance(
            confidence,
            bool,
        )
    ):

        issues.append(
            make_issue(
                ERROR,
                "INVALID_CONFIDENCE_TYPE",
                (
                    f"Confidence must be "
                    f"numeric, got "
                    f"{repr(confidence)}."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    elif not (
        0 <= confidence <= 1
    ):

        issues.append(
            make_issue(
                ERROR,
                "INVALID_CONFIDENCE_RANGE",
                (
                    f"Confidence "
                    f"{confidence} is outside "
                    f"0-1."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    elif (
        confidence
        < confidence_threshold
    ):

        issues.append(
            make_issue(
                WARNING,
                "LOW_CONFIDENCE",
                (
                    f"Classification confidence "
                    f"is {confidence:.2f}, below "
                    f"threshold "
                    f"{confidence_threshold:.2f}."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Review status
    # --------------------------------------------------------

    review_status = record.get(
        "review_status"
    )

    if (
        review_status is not None
        and review_status
        not in VALID_REVIEW_STATUSES
    ):

        issues.append(
            make_issue(
                WARNING,
                "INVALID_REVIEW_STATUS",
                (
                    f"Unknown review status "
                    f"'{review_status}'."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    if (
        review_status
        == "needs_review"
    ):

        issues.append(
            make_issue(
                WARNING,
                "FLAGGED_FOR_REVIEW",
                (
                    "Classifier marked this "
                    "question as needs_review."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Boolean fields
    # --------------------------------------------------------

    for field in [
        "requires_diagram",
        "requires_shared_context",
    ]:

        value = record.get(field)

        if not isinstance(
            value,
            bool,
        ):

            issues.append(
                make_issue(
                    WARNING,
                    "INVALID_BOOLEAN",
                    (
                        f"{field} should be "
                        f"true or false."
                    ),
                    parent_id=parent_id,
                    record_id=record_id,
                    subquestion=subquestion,
                )
            )

    # --------------------------------------------------------
    # Shared context
    # --------------------------------------------------------

    if (
        record.get(
            "requires_shared_context"
        )
        is True
        and is_blank(
            record.get(
                "shared_stem"
            )
        )
    ):

        issues.append(
            make_issue(
                WARNING,
                "MISSING_SHARED_STEM",
                (
                    "Subquestion requires "
                    "shared context but "
                    "shared_stem is empty."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Images
    # --------------------------------------------------------

    images = record.get(
        "question_images",
        [],
    )

    if images is None:
        images = []

    if not isinstance(
        images,
        list,
    ):

        issues.append(
            make_issue(
                ERROR,
                "INVALID_IMAGE_LIST",
                (
                    "question_images must "
                    "be a list."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    else:

        if not images:

            issues.append(
                make_issue(
                    WARNING,
                    "NO_QUESTION_IMAGES",
                    (
                        "No original question "
                        "images are attached."
                    ),
                    parent_id=parent_id,
                    record_id=record_id,
                    subquestion=subquestion,
                )
            )

        for image in images:

            image_path = (
                resolve_project_path(
                    image
                )
            )

            if (
                image_path is not None
                and not image_path.exists()
            ):

                issues.append(
                    make_issue(
                        ERROR,
                        "MISSING_IMAGE_FILE",
                        (
                            f"Image file does "
                            f"not exist: {image}"
                        ),
                        parent_id=parent_id,
                        record_id=record_id,
                        subquestion=subquestion,
                    )
                )

    # --------------------------------------------------------
    # Diagram consistency
    # --------------------------------------------------------

    if (
        record.get(
            "requires_diagram"
        )
        is True
        and not images
    ):

        issues.append(
            make_issue(
                ERROR,
                "DIAGRAM_WITHOUT_IMAGE",
                (
                    "Question requires a "
                    "diagram but has no "
                    "question image."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    # --------------------------------------------------------
    # Source PDF metadata
    # --------------------------------------------------------

    for field in [
        "source_question_pdf",
        "source_mark_scheme_pdf",
    ]:

        source_path = record.get(
            field
        )

        if is_blank(source_path):

            issues.append(
                make_issue(
                    WARNING,
                    "MISSING_SOURCE_PATH",
                    (
                        f"{field} is missing."
                    ),
                    parent_id=parent_id,
                    record_id=record_id,
                    subquestion=subquestion,
                )
            )

            continue

        resolved = resolve_project_path(
            source_path
        )

        if (
            resolved is not None
            and not resolved.exists()
        ):

            issues.append(
                make_issue(
                    WARNING,
                    "SOURCE_FILE_NOT_FOUND",
                    (
                        f"{field} does not "
                        f"exist locally: "
                        f"{source_path}"
                    ),
                    parent_id=parent_id,
                    record_id=record_id,
                    subquestion=subquestion,
                )
            )

    # --------------------------------------------------------
    # Model metadata
    # --------------------------------------------------------

    if is_blank(
        record.get("model")
    ):

        issues.append(
            make_issue(
                INFO,
                "MISSING_MODEL",
                (
                    "No AI model metadata "
                    "stored for this record."
                ),
                parent_id=parent_id,
                record_id=record_id,
                subquestion=subquestion,
            )
        )

    return issues


# ============================================================
# PARENT-LEVEL VALIDATION
# ============================================================

def validate_parent(
    parent_id,
    records,
    source_question,
):

    issues = []

    # --------------------------------------------------------
    # Duplicate subquestion labels
    # --------------------------------------------------------

    labels = [
        record.get(
            "subquestion"
        )
        for record
        in records
        if record.get(
            "subquestion"
        )
    ]

    counts = Counter(labels)

    for label, count in counts.items():

        if count > 1:

            issues.append(
                make_issue(
                    ERROR,
                    "DUPLICATE_SUBQUESTION",
                    (
                        f"Subquestion '{label}' "
                        f"appears {count} times."
                    ),
                    parent_id=parent_id,
                    subquestion=label,
                )
            )

    # --------------------------------------------------------
    # Main + subparts inconsistency
    # --------------------------------------------------------

    if (
        "main" in labels
        and len(labels) > 1
    ):

        issues.append(
            make_issue(
                ERROR,
                "MAIN_WITH_SUBQUESTIONS",
                (
                    "Question contains 'main' "
                    "and additional subquestions."
                ),
                parent_id=parent_id,
            )
        )

    # --------------------------------------------------------
    # Marks
    # --------------------------------------------------------

    expected_marks = (
        source_question.get(
            "marks"
        )
    )

    known_marks = [
        record.get("marks")
        for record
        in records
        if isinstance(
            record.get("marks"),
            int,
        )
        and not isinstance(
            record.get("marks"),
            bool,
        )
    ]

    all_marks_known = (
        len(known_marks)
        == len(records)
    )

    if (
        expected_marks is not None
        and all_marks_known
    ):

        detected_marks = sum(
            known_marks
        )

        if (
            detected_marks
            != expected_marks
        ):

            issues.append(
                make_issue(
                    ERROR,
                    "MARK_TOTAL_MISMATCH",
                    (
                        f"Subquestion marks "
                        f"sum to "
                        f"{detected_marks}, "
                        f"but parent question "
                        f"is worth "
                        f"{expected_marks}."
                    ),
                    parent_id=parent_id,
                )
            )

    elif (
        expected_marks is not None
        and not all_marks_known
    ):

        issues.append(
            make_issue(
                WARNING,
                "INCOMPLETE_MARK_TOTAL",
                (
                    "Cannot verify parent "
                    "mark total because one "
                    "or more subquestion marks "
                    "are missing."
                ),
                parent_id=parent_id,
            )
        )

    # --------------------------------------------------------
    # Metadata consistency
    # --------------------------------------------------------

    metadata_fields = [
        "unit",
        "year",
        "session_code",
        "question_number",
    ]

    for field in metadata_fields:

        source_value = (
            source_question.get(field)
        )

        for record in records:

            record_value = (
                record.get(field)
            )

            if (
                str(record_value)
                != str(source_value)
            ):

                issues.append(
                    make_issue(
                        ERROR,
                        "METADATA_MISMATCH",
                        (
                            f"{field} is "
                            f"'{record_value}' "
                            f"but source question "
                            f"contains "
                            f"'{source_value}'."
                        ),
                        parent_id=parent_id,
                        record_id=(
                            record.get("id")
                        ),
                        subquestion=(
                            record.get(
                                "subquestion"
                            )
                        ),
                    )
                )

    # --------------------------------------------------------
    # Shared stem consistency
    # --------------------------------------------------------

    shared_stems = {
        record.get(
            "shared_stem",
            "",
        ).strip()
        for record
        in records
        if isinstance(
            record.get(
                "shared_stem",
                ""
            ),
            str,
        )
    }

    if len(shared_stems) > 1:

        issues.append(
            make_issue(
                WARNING,
                "INCONSISTENT_SHARED_STEM",
                (
                    "Subquestions under the "
                    "same parent have different "
                    "shared_stem values."
                ),
                parent_id=parent_id,
            )
        )

    return issues


# ============================================================
# COVERAGE VALIDATION
# ============================================================

def validate_coverage(
    source_questions,
    grouped_records,
):

    issues = []

    for source in source_questions:

        parent_id = source.get("id")

        if not parent_id:
            continue

        if (
            parent_id
            not in grouped_records
        ):

            issues.append(
                make_issue(
                    INFO,
                    "NOT_CLASSIFIED",
                    (
                        "Source question has "
                        "not been classified yet."
                    ),
                    parent_id=parent_id,
                )
            )

    return issues


# ============================================================
# DETERMINE PARENT STATUS
# ============================================================

def calculate_parent_statuses(
    source_questions,
    grouped_records,
    issues,
):

    issues_by_parent = defaultdict(
        list
    )

    for issue in issues:

        parent_id = issue.get(
            "parent_question_id"
        )

        if parent_id:

            issues_by_parent[
                parent_id
            ].append(issue)

    statuses = {}

    for source in source_questions:

        parent_id = source.get("id")

        if not parent_id:
            continue

        if (
            parent_id
            not in grouped_records
        ):

            statuses[
                parent_id
            ] = "not_classified"

            continue

        parent_issues = (
            issues_by_parent.get(
                parent_id,
                [],
            )
        )

        has_error = any(
            issue["severity"]
            == ERROR
            for issue
            in parent_issues
        )

        has_warning = any(
            issue["severity"]
            == WARNING
            for issue
            in parent_issues
        )

        if has_error:

            statuses[
                parent_id
            ] = "invalid"

        elif has_warning:

            statuses[
                parent_id
            ] = "needs_review"

        else:

            statuses[
                parent_id
            ] = "valid"

    return statuses


# ============================================================
# REPORT GENERATION
# ============================================================

def build_report(
    source_questions,
    enriched_records,
    issues,
    statuses,
    confidence_threshold,
):

    severity_counts = Counter(
        issue["severity"]
        for issue
        in issues
    )

    issue_code_counts = Counter(
        issue["code"]
        for issue
        in issues
    )

    status_counts = Counter(
        statuses.values()
    )

    units = Counter(
        record.get("unit")
        for record
        in enriched_records
        if record.get("unit")
    )

    difficulties = Counter(
        record.get("difficulty")
        for record
        in enriched_records
        if record.get("difficulty")
    )

    question_types = Counter(
        record.get("question_type")
        for record
        in enriched_records
        if record.get(
            "question_type"
        )
    )

    topics = Counter(
        (
            record.get("unit"),
            record.get("topic"),
        )
        for record
        in enriched_records
        if record.get("topic")
    )

    topic_counts = {}

    for (
        unit,
        topic,
    ), count in topics.items():

        key = (
            f"{unit} | {topic}"
        )

        topic_counts[key] = count

    return {

        "summary": {

            "source_parent_questions": (
                len(source_questions)
            ),

            "enriched_subquestions": (
                len(enriched_records)
            ),

            "classified_parent_questions": (
                len({
                    record.get(
                        "parent_question_id"
                    )
                    for record
                    in enriched_records
                    if record.get(
                        "parent_question_id"
                    )
                })
            ),

            "valid_parent_questions": (
                status_counts.get(
                    "valid",
                    0,
                )
            ),

            "needs_review_parent_questions": (
                status_counts.get(
                    "needs_review",
                    0,
                )
            ),

            "invalid_parent_questions": (
                status_counts.get(
                    "invalid",
                    0,
                )
            ),

            "not_classified_parent_questions": (
                status_counts.get(
                    "not_classified",
                    0,
                )
            ),

            "errors": (
                severity_counts.get(
                    ERROR,
                    0,
                )
            ),

            "warnings": (
                severity_counts.get(
                    WARNING,
                    0,
                )
            ),

            "info": (
                severity_counts.get(
                    INFO,
                    0,
                )
            ),

            "confidence_threshold": (
                confidence_threshold
            ),
        },

        "status_counts": dict(
            status_counts
        ),

        "issue_code_counts": dict(
            issue_code_counts
        ),

        "unit_counts": dict(
            units
        ),

        "difficulty_counts": dict(
            difficulties
        ),

        "question_type_counts": dict(
            question_types
        ),

        "topic_counts": (
            topic_counts
        ),

        "parent_statuses": (
            statuses
        ),

        "issues": issues,
    }


# ============================================================
# CONSOLE OUTPUT
# ============================================================

def print_report(
    report,
    *,
    show_all=False,
):

    summary = report[
        "summary"
    ]

    print()
    print("=" * 72)
    print(
        "EDEXCEL PHYSICS DATABASE VALIDATION"
    )
    print("=" * 72)

    print()

    print(
        f"Source parent questions : "
        f"{summary['source_parent_questions']}"
    )

    print(
        f"Classified parents      : "
        f"{summary['classified_parent_questions']}"
    )

    print(
        f"Enriched subquestions   : "
        f"{summary['enriched_subquestions']}"
    )

    print()

    print(
        f"✓ Valid                 : "
        f"{summary['valid_parent_questions']}"
    )

    print(
        f"⚠ Needs review          : "
        f"{summary['needs_review_parent_questions']}"
    )

    print(
        f"✗ Invalid               : "
        f"{summary['invalid_parent_questions']}"
    )

    print(
        f"- Not classified        : "
        f"{summary['not_classified_parent_questions']}"
    )

    print()

    print(
        f"Errors                   : "
        f"{summary['errors']}"
    )

    print(
        f"Warnings                 : "
        f"{summary['warnings']}"
    )

    print(
        f"Info                     : "
        f"{summary['info']}"
    )

    print()

    print(
        "Issue breakdown:"
    )

    issue_counts = report[
        "issue_code_counts"
    ]

    if not issue_counts:

        print(
            "  No issues found."
        )

    else:

        for code, count in sorted(
            issue_counts.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        ):

            print(
                f"  {code:<32} "
                f"{count}"
            )

    # --------------------------------------------------------
    # Detailed problems
    # --------------------------------------------------------

    problems = [
        issue
        for issue
        in report["issues"]
        if (
            show_all
            or issue["severity"]
            in {
                ERROR,
                WARNING,
            }
        )
    ]

    if problems:

        print()
        print("-" * 72)
        print("PROBLEMS")
        print("-" * 72)

        current_parent = None

        for issue in problems:

            parent = (
                issue.get(
                    "parent_question_id"
                )
                or "DATASET"
            )

            if (
                parent
                != current_parent
            ):

                print()
                print(parent)

                current_parent = parent

            if (
                issue["severity"]
                == ERROR
            ):

                symbol = "✗"

            elif (
                issue["severity"]
                == WARNING
            ):

                symbol = "⚠"

            else:

                symbol = "-"

            suffix = ""

            if issue.get(
                "subquestion"
            ):

                suffix = (
                    f" [{issue['subquestion']}]"
                )

            print(
                f"  {symbol} "
                f"{issue['code']}"
                f"{suffix}: "
                f"{issue['message']}"
            )

    print()
    print("-" * 72)

    print(
        f"Full report saved to:"
    )

    print(
        f"  {REPORT_FILE}"
    )

    print()


# ============================================================
# ARGUMENTS
# ============================================================

def parse_arguments():

    parser = argparse.ArgumentParser(
        description=(
            "Validate enriched Edexcel IAS "
            "Physics question data before "
            "database upload."
        )
    )

    parser.add_argument(
        "--confidence",
        type=float,
        default=(
            DEFAULT_CONFIDENCE_THRESHOLD
        ),
        help=(
            "Confidence threshold below "
            "which a record is flagged. "
            "Default: 0.75"
        ),
    )

    parser.add_argument(
        "--show-all",
        action="store_true",
        help=(
            "Also display informational "
            "issues such as questions that "
            "have not been classified yet."
        ),
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit with code 1 if errors "
            "or warnings are found. Useful "
            "before database deployment."
        ),
    )

    return parser.parse_args()


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_arguments()

    if not (
        0 <= args.confidence <= 1
    ):

        print()
        print(
            "ERROR: --confidence must "
            "be between 0 and 1."
        )
        print()

        sys.exit(1)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    source_questions = load_json(
        SOURCE_FILE
    )

    enriched_records = load_json(
        ENRICHED_FILE
    )

    # --------------------------------------------------------
    # Basic structure
    # --------------------------------------------------------

    issues = (
        validate_dataset_structure(
            source_questions,
            enriched_records,
        )
    )

    if issues:

        report = {
            "summary": {
                "errors": len(issues),
            },
            "issues": issues,
        }

        save_json(
            REPORT_FILE,
            report,
        )

        print()
        print(
            "Dataset structure is invalid."
        )
        print()

        sys.exit(1)

    # --------------------------------------------------------
    # Maps
    # --------------------------------------------------------

    source_map = build_source_map(
        source_questions
    )

    grouped_records = group_by_parent(
        enriched_records
    )

    # --------------------------------------------------------
    # Duplicate IDs
    # --------------------------------------------------------

    issues.extend(
        validate_duplicate_ids(
            enriched_records
        )
    )

    # --------------------------------------------------------
    # Individual records
    # --------------------------------------------------------

    for record in enriched_records:

        issues.extend(
            validate_record(
                record,
                source_map,
                args.confidence,
            )
        )

    # --------------------------------------------------------
    # Parent questions
    # --------------------------------------------------------

    for (
        parent_id,
        records,
    ) in grouped_records.items():

        source_question = (
            source_map.get(
                parent_id
            )
        )

        if (
            source_question
            is None
        ):
            continue

        issues.extend(
            validate_parent(
                parent_id,
                records,
                source_question,
            )
        )

    # --------------------------------------------------------
    # Classification coverage
    # --------------------------------------------------------

    issues.extend(
        validate_coverage(
            source_questions,
            grouped_records,
        )
    )

    # --------------------------------------------------------
    # Parent statuses
    # --------------------------------------------------------

    statuses = (
        calculate_parent_statuses(
            source_questions,
            grouped_records,
            issues,
        )
    )

    # --------------------------------------------------------
    # Build report
    # --------------------------------------------------------

    report = build_report(
        source_questions,
        enriched_records,
        issues,
        statuses,
        args.confidence,
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    save_json(
        REPORT_FILE,
        report,
    )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print_report(
        report,
        show_all=args.show_all,
    )

    # --------------------------------------------------------
    # Strict mode
    # --------------------------------------------------------

    if args.strict:

        summary = report[
            "summary"
        ]

        if (
            summary["errors"] > 0
            or summary["warnings"] > 0
        ):

            sys.exit(1)


if __name__ == "__main__":
    main()