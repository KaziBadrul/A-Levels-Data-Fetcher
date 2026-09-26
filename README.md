# Edexcel IAL Physics WPH11/WPH12 Downloader

Downloads publicly accessible Pearson-hosted question papers and mark schemes
for:

- WPH11: Unit 1, Mechanics and Materials
- WPH12: Unit 2, Waves and Electricity

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Test first

```bash
python download_papers.py --dry-run
```

## Download

```bash
python download_papers.py
```

## Examples

Only Unit 1:

```bash
python download_papers.py --units WPH11
```

Only 2022 through 2025:

```bash
python download_papers.py --start-year 2022 --end-year 2025
```

Custom folder:

```bash
python download_papers.py --out ./past_papers
```

## Output

```text
data/
├── WPH11/
│   ├── 2023_JAN/
│   │   ├── question.pdf
│   │   └── mark_scheme.pdf
│   └── ...
└── WPH12/
    └── ...
```

The script does not log into Pearson or attempt to bypass locked/restricted
materials. A candidate file is saved only if the Pearson URL itself returns
a valid PDF.
