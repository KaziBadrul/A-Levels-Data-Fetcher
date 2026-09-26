# Edexcel IAS Physics Question Bank Pipeline

A Python pipeline for downloading, extracting, classifying, and
validating Pearson Edexcel International AS Level Physics past-paper
questions.

The project currently supports:

-   **WPH11** - Mechanics and Materials
-   **WPH12** - Waves and Electricity

The pipeline downloads question papers and mark schemes, extracts
individual questions and their original visuals, uses Gemini to split
and classify questions, and validates the resulting dataset before it is
uploaded to a database or used by a web application.

------------------------------------------------------------------------

## Pipeline Overview

``` text
Physics & Maths Tutor / Past Papers
              |
              v
      download_papers.py
              |
              v
       data/WPH11/
       data/WPH12/
              |
              v
      extract_questions.py
              |
              v
       output/questions.json
       output/.../images/
              |
              v
      classify_questions.py
              |
              v
 output/enriched_questions.json
 output/classification_status.json
              |
              v
      validate_questions.py
              |
              v
 output/validation_report.json
              |
              v
       Database / Website
```

The four main scripts are:

  -----------------------------------------------------------------------
  Script                              Purpose
  ----------------------------------- -----------------------------------
  `download_papers.py`                Finds and downloads question papers
                                      and mark schemes

  `extract_questions.py`              Extracts individual questions,
                                      text, metadata, mark-scheme text,
                                      and question images

  `classify_questions.py`             Uses Gemini to split questions into
                                      subquestions and classify them

  `validate_questions.py`             Checks the final dataset for
                                      errors, warnings, missing files,
                                      and suspicious AI output
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 1. Project Structure

The project should look approximately like this:

``` text
physics-question-bank/
|
├── .env
├── .gitignore
├── .venv/
|
├── README.md
├── taxonomy.py
|
├── download_papers.py
├── extract_questions.py
├── classify_questions.py
├── validate_questions.py
|
├── data/
│   |
│   ├── WPH11/
│   │   ├── 2019_JAN/
│   │   │   ├── question.pdf
│   │   │   └── mark_scheme.pdf
│   │   |
│   │   ├── 2019_MAY_JUNE/
│   │   │   ├── question.pdf
│   │   │   └── mark_scheme.pdf
│   │   |
│   │   └── ...
│   |
│   └── WPH12/
│       ├── 2019_JAN/
│       │   ├── question.pdf
│       │   └── mark_scheme.pdf
│       |
│       └── ...
|
└── output/
    |
    ├── questions.json
    ├── enriched_questions.json
    ├── classification_status.json
    ├── validation_report.json
    |
    ├── WPH11/
    │   ├── 2019_JAN/
    │   │   ├── questions.json
    │   │   └── images/
    │   │       ├── WPH11_2019_JAN_Q01_p1.png
    │   │       ├── WPH11_2019_JAN_Q02_p1.png
    │   │       └── ...
    │   └── ...
    |
    └── WPH12/
        └── ...
```

Not every generated file will exist immediately. They are created as you
progress through the pipeline.

------------------------------------------------------------------------

# 2. Requirements

You need:

-   Python 3.10 or newer
-   Internet access for downloading papers
-   A Gemini API key for `classify_questions.py`
-   A Python virtual environment

Check your Python version:

``` bash
python3 --version
```

On macOS, especially when Python is installed through Homebrew, do not
install the project packages globally. Use a virtual environment.

------------------------------------------------------------------------

# 3. Initial Setup

Open Terminal and navigate to the project:

``` bash
cd /path/to/physics-question-bank
```

For example:

``` bash
cd ~/Documents/physics-question-bank
```

## Create a virtual environment

``` bash
python3 -m venv .venv
```

Activate it:

``` bash
source .venv/bin/activate
```

Your terminal should now start with something similar to:

``` text
(.venv)
```

Upgrade pip:

``` bash
python -m pip install --upgrade pip
```

Install the required packages:

``` bash
pip install \
    requests \
    beautifulsoup4 \
    pymupdf \
    google-genai \
    pydantic \
    python-dotenv
```

You can verify the installation with:

``` bash
pip list
```

------------------------------------------------------------------------

# 4. Gemini API Key

`classify_questions.py` requires a Gemini API key.

Create a file called:

``` text
.env
```

in the root of the project.

The project should look like:

``` text
physics-question-bank/
├── .env
├── classify_questions.py
├── ...
```

Inside `.env`, add:

``` env
GEMINI_API_KEY=YOUR_ACTUAL_API_KEY
```

Do not add quotes unless they are actually part of the key.

------------------------------------------------------------------------

# 5. Git Ignore

Create a `.gitignore` file in the project root:

``` gitignore
.venv/
.env
__pycache__/
*.pyc
```

The `.env` file contains your API key and should never be committed to
Git.

Depending on how you want to manage generated data, you may also choose
to ignore some or all of:

``` gitignore
output/
```

Do this only if you do not want generated classification data tracked by
Git.

------------------------------------------------------------------------

# 6. Using the Project

The scripts should normally be run in this order:

``` text
1. download_papers.py
2. extract_questions.py
3. classify_questions.py
4. validate_questions.py
```

Each stage depends on output from the previous stage.

Before running any script in a new terminal session:

``` bash
cd /path/to/physics-question-bank
source .venv/bin/activate
```

------------------------------------------------------------------------

# 7. Step 1: Download Past Papers

Run:

``` bash
python download_papers.py
```

The downloader discovers available WPH11 and WPH12 papers and downloads
the question paper and corresponding mark scheme.

The resulting structure should resemble:

``` text
data/
├── WPH11/
│   ├── 2019_JAN/
│   │   ├── question.pdf
│   │   └── mark_scheme.pdf
│   ├── 2019_MAY_JUNE/
│   │   ├── question.pdf
│   │   └── mark_scheme.pdf
│   └── ...
│
└── WPH12/
    └── ...
```

Each session folder contains:

``` text
question.pdf
mark_scheme.pdf
```

The downloader is designed to discover available papers rather than
requiring every year and session to be hard-coded.

It also checks existing downloads, so rerunning it should not require
you to manually rebuild the `data/` directory.

## When should you rerun it?

Rerun:

``` bash
python download_papers.py
```

when new exam papers become available.

------------------------------------------------------------------------

# 8. Step 2: Extract Questions

After downloading the papers, run:

``` bash
python extract_questions.py
```

This processes the question papers and mark schemes.

It extracts:

-   individual parent questions
-   question text
-   question number
-   total marks
-   paper metadata
-   approximate matching mark-scheme text
-   source page numbers
-   original question images

The master output is:

``` text
output/questions.json
```

It also creates per-session output such as:

``` text
output/
└── WPH11/
    └── 2024_JAN/
        ├── questions.json
        └── images/
            ├── WPH11_2024_JAN_Q01_p1.png
            ├── WPH11_2024_JAN_Q02_p1.png
            └── ...
```

The images are important because PDF text extraction can lose or
distort:

-   equations
-   graphs
-   diagrams
-   circuits
-   tables
-   mathematical notation
-   multi-column layouts

The original rendered question is therefore retained alongside the
extracted text.

## Extract everything

``` bash
python extract_questions.py
```

## Extract only WPH11

``` bash
python extract_questions.py --unit WPH11
```

## Extract only WPH12

``` bash
python extract_questions.py --unit WPH12
```

## Extract one session

For example:

``` bash
python extract_questions.py \
    --unit WPH11 \
    --session 2024_JAN
```

Testing a single session before processing the entire archive is useful
when changing extraction logic.

------------------------------------------------------------------------

# 9. Step 3: Classify and Split Questions

Once `output/questions.json` exists, run:

``` bash
python classify_questions.py
```

The classifier uses Gemini with both:

-   extracted text
-   original rendered question images

It uses the images to help recover information that may have been lost
during PDF text extraction.

The classifier can:

-   identify the exact subquestion structure
-   split parent questions into subquestions
-   preserve shared question context
-   match mark-scheme content to each subquestion
-   classify topics
-   classify subtopics
-   assign difficulty
-   assign question type
-   identify skills
-   identify whether a diagram is required
-   assign classification confidence

The taxonomy comes from:

``` text
taxonomy.py
```

Gemini is instructed to select topics from this controlled taxonomy
rather than inventing arbitrary topic names.

------------------------------------------------------------------------

# 10. Selecting a Gemini Model

When you run:

``` bash
python classify_questions.py
```

the script can present an interactive model selector.

For example:

``` text
========================================================================
SELECT GEMINI MODEL
========================================================================

[1] Gemini Flash
    <model-id>

[2] Gemini Flash-Lite
    <model-id>

[3] Gemini Pro
    <model-id>

Select model [1-3]:
```

Choose the model you want to use for that run.

The exact available model IDs depend on the models configured in
`classify_questions.py` and your Gemini API access.

The model used for each classified record is stored in the output
metadata.

## Non-interactive model selection

If your version of `classify_questions.py` supports `--model`, you can
bypass the interactive selector:

``` bash
python classify_questions.py \
    --model YOUR_MODEL_ID
```

This is useful for future automation.

------------------------------------------------------------------------

# 11. Classification Output

The main output is:

``` text
output/enriched_questions.json
```

A classified subquestion can contain information such as:

``` json
{
  "id": "WPH11-2024-JAN-Q14-ai",
  "parent_question_id": "WPH11-2024-JAN-Q14",
  "question_number": "14",
  "subquestion": "a(i)",
  "unit": "WPH11",
  "year": 2024,
  "session": "January",
  "shared_stem": "...",
  "question_text": "...",
  "marks": 2,
  "mark_scheme": "...",
  "topic": "Mechanics",
  "subtopic": "Momentum",
  "secondary_subtopics": [],
  "difficulty": "Medium",
  "question_type": "Calculation",
  "skills": [
    "algebra",
    "physics reasoning"
  ],
  "requires_diagram": true,
  "requires_shared_context": true,
  "classification_confidence": 0.94,
  "review_status": "completed",
  "model": "..."
}
```

The exact contents depend on the current version of the classifier.

------------------------------------------------------------------------

# 12. Classification Checkpoints and Resume

`classify_questions.py` is designed to save successful work
incrementally.

The two important files are:

``` text
output/enriched_questions.json
output/classification_status.json
```

`enriched_questions.json` contains the actual classified dataset.

`classification_status.json` records processing information such as:

``` text
completed
needs_review
failed
```

It can also track:

-   attempt count
-   last error
-   confidence
-   warnings
-   number of detected subquestions

## If the Gemini quota runs out

Suppose the classifier successfully processes questions 1 through 80 and
then fails on question 81.

The first 80 questions have already been saved.

After your quota becomes available again, simply run:

``` bash
python classify_questions.py
```

Completed questions are skipped.

The classifier continues with unfinished or failed questions.

This prevents wasting Gemini tokens by reprocessing successful
questions.

------------------------------------------------------------------------

# 13. Retry Failed Questions

To retry questions recorded as failed:

``` bash
python classify_questions.py --retry-failed
```

Successfully completed questions remain untouched.

------------------------------------------------------------------------

# 14. Reprocess a Question

Normally, completed questions are skipped.

If you intentionally want to redo a question, use `--force`.

For example:

``` bash
python classify_questions.py \
    --unit WPH11 \
    --year 2024 \
    --session JAN \
    --question 14 \
    --force
```

This is useful when:

-   a question was classified incorrectly
-   you changed the taxonomy
-   you improved the prompt
-   you want to classify it with another model

The old records for that parent question are replaced by the newly
generated records.

------------------------------------------------------------------------

# 15. Process Only Specific Questions

## One unit

``` bash
python classify_questions.py \
    --unit WPH11
```

## One year

``` bash
python classify_questions.py \
    --year 2024
```

## One session

``` bash
python classify_questions.py \
    --session JAN
```

## One question

``` bash
python classify_questions.py \
    --unit WPH11 \
    --year 2024 \
    --session JAN \
    --question 14
```

These filters can be combined.

------------------------------------------------------------------------

# 16. Limit Classification During Testing

When testing a new prompt, model, or code change, avoid immediately
processing the whole archive.

If supported by your classifier, use:

``` bash
python classify_questions.py --limit 10
```

This processes at most 10 new questions.

Then run it again:

``` bash
python classify_questions.py --limit 10
```

Previously completed questions are skipped and the next batch is
processed.

This is useful for controlling API usage while testing.

------------------------------------------------------------------------

# 17. Step 4: Validate the Dataset

After classification, run:

``` bash
python validate_questions.py
```

This stage is completely local.

It does not need Gemini and does not consume Gemini API tokens.

The validator checks the classified dataset against:

``` text
output/questions.json
output/enriched_questions.json
taxonomy.py
question image files
source PDF files
```

It checks for problems including:

-   duplicate IDs
-   missing parent IDs
-   missing question text
-   empty mark schemes
-   missing marks
-   invalid marks
-   invalid units
-   invalid topics
-   invalid subtopics
-   invalid secondary subtopics
-   invalid difficulty labels
-   invalid question types
-   missing confidence
-   low confidence
-   invalid review status
-   inconsistent shared context
-   missing question images
-   missing source files
-   diagram questions without images
-   duplicate subquestion labels
-   incorrect parent mark totals
-   source/classified metadata mismatches
-   questions that have not yet been classified

------------------------------------------------------------------------

# 18. Validation Output

Run:

``` bash
python validate_questions.py
```

You should get a summary similar to:

``` text
========================================================================
EDEXCEL PHYSICS DATABASE VALIDATION
========================================================================

Source parent questions : 487
Classified parents      : 487
Enriched subquestions   : 1032

✓ Valid                 : 451
⚠ Needs review          : 29
✗ Invalid               : 7
- Not classified        : 0

Errors                   : 8
Warnings                 : 41
Info                     : 0
```

The complete report is written to:

``` text
output/validation_report.json
```

This provides a machine-readable list of every detected issue.

------------------------------------------------------------------------

# 19. Validation Confidence Threshold

The default confidence threshold is:

``` text
0.75
```

Questions below this level are flagged for review.

You can change the threshold:

``` bash
python validate_questions.py \
    --confidence 0.85
```

This does not reclassify anything.

It only changes what the validator considers low confidence.

------------------------------------------------------------------------

# 20. Show Informational Validation Results

By default, the terminal focuses on errors and warnings.

To also show informational results:

``` bash
python validate_questions.py \
    --show-all
```

For example, this can show questions that have not yet been classified.

------------------------------------------------------------------------

# 21. Strict Validation

Before uploading the dataset to a production database, use:

``` bash
python validate_questions.py \
    --strict
```

Strict mode exits with a failure code if errors or warnings are present.

This makes it useful later in an automated pipeline:

``` text
classify_questions.py
        |
        v
validate_questions.py --strict
        |
        +---- FAIL ----> Stop
        |
        +---- PASS ----> Upload to database
```

The validator is intentionally read-only. It reports problems but does
not automatically delete or modify your classified data.

------------------------------------------------------------------------

# 22. Recommended Full Workflow

For a completely fresh project:

## 1. Activate environment

``` bash
source .venv/bin/activate
```

## 2. Download papers

``` bash
python download_papers.py
```

## 3. Extract questions

``` bash
python extract_questions.py
```

## 4. Test classification on a small sample

``` bash
python classify_questions.py \
    --unit WPH11 \
    --year 2024 \
    --session JAN \
    --question 14
```

Inspect the result.

## 5. Run a small batch

``` bash
python classify_questions.py \
    --limit 10
```

## 6. Validate

``` bash
python validate_questions.py
```

## 7. Classify the remaining dataset

``` bash
python classify_questions.py
```

## 8. Final validation

``` bash
python validate_questions.py
```

## 9. Production check

``` bash
python validate_questions.py --strict
```

------------------------------------------------------------------------

# 23. Updating the Dataset When New Papers Appear

You do not need to rebuild the project manually.

Run:

``` bash
python download_papers.py
```

Then:

``` bash
python extract_questions.py
```

Then:

``` bash
python classify_questions.py
```

The classifier should skip questions already stored in the enriched
dataset and process new questions.

Finally:

``` bash
python validate_questions.py
```

The intended update cycle is therefore:

``` text
New exam session released
        |
        v
download_papers.py
        |
        v
extract_questions.py
        |
        v
classify_questions.py
        |
        v
validate_questions.py
```

------------------------------------------------------------------------

# 24. Common Commands

## Activate environment

``` bash
source .venv/bin/activate
```

## Download papers

``` bash
python download_papers.py
```

## Extract all questions

``` bash
python extract_questions.py
```

## Extract one unit

``` bash
python extract_questions.py --unit WPH11
```

## Classify everything

``` bash
python classify_questions.py
```

## Classify one question

``` bash
python classify_questions.py \
    --unit WPH11 \
    --year 2024 \
    --session JAN \
    --question 14
```

## Process only 10 new questions

``` bash
python classify_questions.py \
    --limit 10
```

## Retry failures

``` bash
python classify_questions.py \
    --retry-failed
```

## Force reclassification

``` bash
python classify_questions.py \
    --unit WPH11 \
    --year 2024 \
    --session JAN \
    --question 14 \
    --force
```

## Validate

``` bash
python validate_questions.py
```

## Validate with a higher confidence threshold

``` bash
python validate_questions.py \
    --confidence 0.85
```

## Strict validation

``` bash
python validate_questions.py \
    --strict
```

------------------------------------------------------------------------

# 25. Important Generated Files

## `data/`

Contains the original downloaded question papers and mark schemes.

Do not treat this as the final application database.

------------------------------------------------------------------------

## `output/questions.json`

Generated by:

``` text
extract_questions.py
```

Contains extracted parent questions before AI enrichment.

This is the input to `classify_questions.py`.

------------------------------------------------------------------------

## `output/enriched_questions.json`

Generated by:

``` text
classify_questions.py
```

This is the primary enriched dataset.

It contains subquestions and classification metadata.

This will eventually be the main source for uploading questions into the
production database.

------------------------------------------------------------------------

## `output/classification_status.json`

Generated by:

``` text
classify_questions.py
```

Tracks processing/checkpoint information.

This allows classification to resume safely after:

-   quota exhaustion
-   API failures
-   network problems
-   crashes
-   manual interruption

Do not delete it unless you intentionally want to reset classification
status.

------------------------------------------------------------------------

## `output/validation_report.json`

Generated by:

``` text
validate_questions.py
```

Contains the complete validation report.

Use it to identify questions that:

-   are invalid
-   need manual review
-   have low confidence
-   contain missing information

------------------------------------------------------------------------

## `taxonomy.py`

Defines the controlled topic/subtopic taxonomy used by the classifier
and validator.

Both scripts depend on it:

``` text
classify_questions.py
validate_questions.py
```

Be careful when changing taxonomy names after questions have already
been classified because existing records may then fail validation.

------------------------------------------------------------------------

# 26. Troubleshooting

## `externally-managed-environment`

If macOS/Homebrew gives:

``` text
error: externally-managed-environment
```

do not use:

``` bash
--break-system-packages
```

Instead create and activate the virtual environment:

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

Then install packages inside it.

------------------------------------------------------------------------

## `ModuleNotFoundError`

Make sure the virtual environment is active:

``` bash
source .venv/bin/activate
```

Then install the dependencies again:

``` bash
pip install \
    requests \
    beautifulsoup4 \
    pymupdf \
    google-genai \
    pydantic \
    python-dotenv
```

------------------------------------------------------------------------

## `GEMINI_API_KEY not found`

Check that:

``` text
.env
```

exists in the project root and contains:

``` env
GEMINI_API_KEY=YOUR_ACTUAL_API_KEY
```

Then rerun:

``` bash
python classify_questions.py
```

------------------------------------------------------------------------

## Gemini quota or rate-limit error

Do not delete your output.

The classifier saves successful questions as it progresses.

After quota becomes available again:

``` bash
python classify_questions.py
```

Completed questions should be skipped automatically.

Or retry recorded failures:

``` bash
python classify_questions.py \
    --retry-failed
```

------------------------------------------------------------------------

## Wrong classification

Reprocess only the affected question:

``` bash
python classify_questions.py \
    --unit WPH11 \
    --year 2024 \
    --session JAN \
    --question 14 \
    --force
```

Select a different model if desired.

Then validate again:

``` bash
python validate_questions.py
```

------------------------------------------------------------------------

## Missing question images

First inspect:

``` text
output/<UNIT>/<SESSION>/images/
```

If extraction failed, rerun the appropriate extraction command.

For example:

``` bash
python extract_questions.py \
    --unit WPH11 \
    --session 2024_JAN
```

Then rerun validation.

------------------------------------------------------------------------

# 27. Development Principles

The pipeline intentionally separates deterministic processing from AI
processing.

``` text
Downloading
    |
    v
Deterministic extraction
    |
    v
AI enrichment
    |
    v
Deterministic validation
```

This makes the dataset easier to inspect, reproduce, and debug.

The original question images are retained because extracted PDF text
should not be treated as the authoritative representation of physics
questions containing equations, diagrams, graphs, and tables.

AI-generated classifications should also not be treated as
unquestionable ground truth. Confidence values and validation warnings
exist so suspicious records can be reviewed.

------------------------------------------------------------------------

# 28. Current Pipeline Status

``` text
[✓] Paper discovery and downloading
[✓] Question/mark-scheme extraction
[✓] Original question image extraction
[✓] Gemini subquestion parsing
[✓] Topic classification
[✓] Difficulty classification
[✓] Question-type classification
[✓] Mark-scheme matching
[✓] Resume/checkpoint system
[✓] Dataset validation
[ ] Production database
[ ] Image storage
[ ] Web application
[ ] Practice system
[ ] User progress tracking
```

The next major stage after the local dataset passes validation is
typically:

``` text
enriched_questions.json
        |
        v
Production Database
        |
        v
Question Bank Web Application
```

------------------------------------------------------------------------

# 29. Quick Start

For future reference, the shortest version of the workflow is:

``` bash
cd /path/to/physics-question-bank

source .venv/bin/activate

python download_papers.py

python extract_questions.py

python classify_questions.py

python validate_questions.py
```

If everything validates successfully, the dataset is ready for the next
database/import stage.

------------------------------------------------------------------------

# 30. Deactivate the Environment

When finished:

``` bash
deactivate
```

To work on the project again later:

``` bash
cd /path/to/physics-question-bank
source .venv/bin/activate
```

Then continue with whichever stage you need.
