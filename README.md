# VoltMart Electronics Demand Forecasting

## Task 1: Data Cleaning Pipeline

A reproducible Python pipeline that validates electronics-store sales,
separates unusable records, and produces clean data and a quality report.

This repository currently implements data preparation, not forecasting.

## Data source

The data is synthetic, not actual VoltMart client data.
It represents one store from 1 May to 31 October 2026.
Product prices and sales patterns are illustrative assumptions.

See data/README.md for the schema and intentionally introduced errors.

## Requirements

- Python 3.14 (used during development)
- PowerShell instructions below
- Python dependencies in requirements.txt

## Setup

Clone this repository, open a terminal in its root folder, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, commands can be run directly through
the environment's interpreter, for example:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Generate and clean the sample

```powershell
python src/generate_sample_data.py
python src/clean_data.py
```

The generator uses seed 42 and overwrites the raw sample.
The cleaner overwrites its output files.

## Output files

| File | Purpose |
|---|---|
| data/processed/sales_clean.csv | Valid records sorted by date, product and line ID |
| data/processed/sales_rejected.csv | Original rejected records with rejection reasons |
| reports/cleaning_report.json | Row counts, repairs and rejection counts |

Exact duplicate records are counted and removed; they are not included
in the rejected-record file.

## Cleaning rules

- Require all eight sales columns.
- Trim surrounding whitespace and treat blank strings as missing.
- Remove exact duplicates after whitespace normalization.
- Reject conflicting records sharing a line ID.
- Require transaction IDs and line IDs.
- Require valid dates in YYYY-MM-DD format.
- Require product IDs that exist in the catalogue.
- Restore missing product names and categories from the static catalogue.
- Reject supplied names or categories that conflict with the catalogue.
- Require positive whole-number quantities.
- Require positive, finite unit prices.
- Preserve original rejected values and record all rejection reasons.

Prices may differ from the catalogue's illustrative reference prices.

## Decisions and trade-offs

### Reject missing quantities and prices

The pipeline does not replace these values with a dataset-wide average.
This avoids using future sales information to alter past records and
avoids inventing transaction values.

Trade-off: rejected sales reduce usable data and may cause daily sales
totals to be understated. Rejected records must be investigated before
using the output for real inventory decisions.

### Restore descriptive metadata from the catalogue

Missing product names and categories are restored using product IDs.
The sample catalogue is treated as fixed, authoritative metadata.

Trade-off: this assumes the catalogue is correct. Real changing
catalogues may require effective dates and historical versions.

### Reject conflicting line IDs

After exact duplicates are removed, all remaining records sharing a
line ID are rejected rather than choosing one arbitrarily.

Trade-off: potentially valid records are withheld until the conflict
can be resolved.

## Run tests

```powershell
python -m pytest -q
```

Tests cover valid records, duplicates, invalid values, catalogue repairs,
conflicting IDs, missing columns, empty files, missing files, command-line
errors, and expected sample results.

A regression test checks that appending a distinct later sale does not
change earlier cleaning results. This does not establish that every
possible future forecasting workflow is free of leakage.

## Expected sample results

The current generated sample produces:

- Input rows: 3,038
- Duplicate rows removed: 5
- Rejected rows: 30
- Clean rows: 3,003
- Missing product names restored: 4
- Whitespace cells trimmed: 4

Row accounting:

3,038 = 5 + 30 + 3,003

## Error handling

Missing files, empty files, missing columns and invalid catalogues produce
clear error messages and a nonzero exit status.

Invalid individual sales records are written to the rejected-record file.
If no usable sales remain, outputs are written and the command exits
with an explanatory error.

Example failure check:

```powershell
python src/clean_data.py --input data/raw/does_not_exist.csv
```

Expected: a "File not found" message and no Python traceback.

## Limitations and next steps

- Synthetic data demonstrates functionality, not real-world accuracy.
- Returns, multiple stores, inventory availability and stockouts are
  outside the current sample.
- Missing records do not automatically mean zero sales.
- Observed sales may underestimate demand during stockouts.
- Daily aggregation, forecasting and time-based model evaluation will
  be implemented in later tasks.