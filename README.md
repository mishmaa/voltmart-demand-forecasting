# VoltMart Electronics Demand Forecasting

A project to forecast daily electronics sales and support stock planning.

Currently implemented:

- Task 1: Sales data cleaning pipeline — accepted.
- Task 2: Daily aggregation and weekly seasonal naive baseline —
  implemented, with final verification in progress.

## Data source

The dataset is synthetic, not actual VoltMart client data.

It represents one electronics store from 1 May to 31 October 2026,
with 12 products. Prices are in Pakistani rupees (PKR).

Product prices, weekend activity, and growth patterns are illustrative
assumptions, not findings about VoltMart's actual customers.

See [data/README.md](data/README.md) for the sales schema and deliberately
introduced errors.

## Requirements

- Python 3.10 or newer.
- Tested on Python 3.10.11 and Python 3.14.
- Intermediate Python versions have not been individually tested.
- Commands below use Windows PowerShell.

requirements.txt contains dependency ranges for compatible installation.
requirements-py310.txt and requirements-py314.txt preserve the exact
dependency versions from the tested environments.

## Setup

Clone the repository and enter its root folder:

```powershell
git clone https://github.com/mishmaa/voltmart-demand-forecasting.git
cd voltmart-demand-forecasting
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use the environment's interpreter
directly, for example:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The same interpreter can run the scripts and tests without activation.

## Run the complete workflow

Run these commands from the repository root:

```powershell
python src/generate_sample_data.py
python src/clean_data.py
python src/build_daily_sales.py
python src/baseline.py
python -m pytest -q
```

The generator uses seed 42 and overwrites the synthetic raw sample.
The remaining scripts overwrite their respective output files.

## Project structure

```text
data/
  README.md
  raw/
    products.csv
    sales_raw.csv
  processed/
    sales_clean.csv
    sales_rejected.csv
    daily_sales.csv
reports/
  cleaning_report.json
  baseline/
    predictions.csv
    per_product_metrics.csv
    metrics.json
src/
  generate_sample_data.py
  clean_data.py
  build_daily_sales.py
  baseline.py
tests/
  test_clean_data.py
  test_baseline.py
README.md
requirements.txt
.gitignore
```

## Task 1: Data cleaning pipeline

The cleaning pipeline validates transaction lines, repairs supported
metadata issues, separates unusable records, and produces a quality report.

### Run

```powershell
python src/clean_data.py
```

### Cleaning rules

- Require all eight sales columns.
- Trim surrounding whitespace and treat blank strings as missing.
- Remove exact duplicate records after whitespace normalization.
- Reject conflicting records sharing a line ID.
- Require transaction IDs and line IDs.
- Require valid dates in YYYY-MM-DD format.
- Require product IDs that exist in the catalogue.
- Restore missing product names and categories from the static catalogue.
- Reject supplied names or categories that conflict with the catalogue.
- Require positive, finite, whole-number quantities within the supported
  integer range.
- Require positive, finite unit prices.
- Preserve original rejected values and record rejection reasons.

Transaction prices may differ from the catalogue's reference prices.

Exact duplicate records are counted and removed; they are not included
in the rejected-record file.

### Cleaning decisions and trade-offs

#### Reject missing quantities and prices

The pipeline does not fill these values using a dataset-wide average.
This avoids inventing transaction values and using future sales
observations to repair earlier transactions.

Trade-off: rejecting records loses usable sales information. Aggregating
only the remaining rows could understate totals, so Task 2 marks affected
daily totals as unknown.

#### Restore descriptive metadata from the catalogue

Missing product names and categories are restored using product IDs.
The synthetic catalogue is treated as fixed, authoritative metadata.

Trade-off: this assumes the catalogue is correct. Real catalogues that
change over time may require historical versions and effective dates.

#### Reject conflicting line IDs

After exact duplicates are removed, all remaining records sharing a line
ID are rejected rather than choosing one arbitrarily.

Trade-off: potentially valid records are withheld until the conflict
can be resolved.

### Cleaning results

| Measure | Result |
|---|---:|
| Input rows | 3,038 |
| Duplicate rows removed | 5 |
| Rejected rows | 30 |
| Clean rows | 3,003 |
| Missing product names restored | 4 |
| Whitespace cells trimmed | 4 |

Row accounting:

```text
3,038 input = 5 duplicates + 30 rejected + 3,003 clean
```

## Task 2: Daily sales and baseline forecast

### Forecast target

Daily units sold per product.

Each daily total is the sum of transaction quantities, not the number
of transaction rows. Sales are an imperfect proxy for demand because
inventory availability and stockouts are not represented.

### Daily aggregation

```powershell
python src/build_daily_sales.py
```

The script reads clean sales, rejected records, raw sales, and the product
catalogue. It creates one row per date and product across the date range
found in valid raw dates.

The current sample contains 184 days and 12 products: 2,208 daily rows.

| Column | Meaning |
|---|---|
| date | Calendar date |
| product_id | Product identifier |
| daily_units | Units sold, or an empty value when unknown |
| status | observed, assumed_zero, or unknown |

### Missing-data assumption and trade-off

Retain all 12 products.

Under the synthetic generator's complete-recording assumption, an absent
product-day represents zero sales only where rejected records do not
introduce uncertainty.

- observed: sum of valid sales quantities, with no identified uncertainty.
- assumed_zero: no sales recorded for that product-day and no identified
  uncertainty.
- unknown: rejected records make the total uncertain, even when some valid
  sales remain.

For a rejected record with an invalid date, the script uses another raw
line from the same transaction only if it supplies one unambiguous date.
This relies on the synthetic rule that transaction lines share a date.

If the date remains unresolved, the affected product's entire period is
marked unknown. An unknown product ID with a valid date makes all products
uncertain on that date. If neither can be located, the entire table is
marked uncertain.

Trade-off: these conservative rules avoid false zeros and incomplete
totals, but substantially reduce evaluation coverage. For real data,
zero filling would require evidence of complete recording.

Current daily statuses:

| Status | Product-days |
|---|---:|
| observed | 1,221 |
| assumed_zero | 385 |
| unknown | 602 |
| Total | 2,208 |

### Baseline method and reason

Use a weekly seasonal naive forecast:

```text
Prediction for product P on day D = units for product P on day D − 7
```

This provides a simple benchmark for the weekly pattern built into the
synthetic sample. It has no fitted parameters.

Trade-off: it is transparent and easy to reproduce, but cannot directly
adapt to promotions, changing trends, holidays, or stockouts.

Future models should be compared against this baseline using the same
evaluation rows.

### Run the baseline

```powershell
python src/baseline.py
```

To select another daily input file:

```powershell
python src/baseline.py --input data/processed/daily_sales.csv
```

### Walk-forward evaluation

Evaluation advances one day at a time. Each prediction uses a value from
exactly seven calendar days earlier, rather than seven transaction rows.

The first seven days per product are warm-up and excluded from eligible
evaluation days. As evaluation advances, earlier actual observations
become available for later predictions.

- A prediction requires a known seven-day-old value.
- Scoring requires both a prediction and a known actual total.
- Unknown historical values are not replaced with zero.
- Unknown actual totals are excluded from scoring.
- Products with no scored days remain visible in the per-product report.

This baseline requires no refitting because it has no learned parameters.

### Score: mean absolute error

MAE measures the average absolute prediction error in units:

```text
MAE = sum of |actual − prediction| / number of scored product-days
```

Overall MAE gives equal weight to each scored product-day.
Coverage is reported alongside MAE so missing evaluations remain visible.

### Current baseline results

| Measure | Result |
|---|---:|
| Eligible product-days after warm-up | 2,124 |
| Available predictions | 1,545 |
| Scored product-days | 1,497 |
| Scoring coverage | 70.48% |
| Overall MAE | Approximately 1.966 units |

The average absolute miss is approximately two units per scored product-day.

PRD-001, PRD-008, and PRD-009 have no evaluable forecasts under the
uncertainty policy. Their MAE is unavailable, not zero.

These results summarize only scored rows in synthetic data. They do not
establish real-world forecast accuracy.

### Evaluation limitation

The daily table uses a full-dataset quality audit, including transaction
date recovery and conservative uncertainty flags.

Evaluation is therefore retrospective on a fixed audited dataset.
Record arrival timestamps are unavailable, so it does not reproduce
historical availability of corrections or quality flags.

The forecast rule itself uses only the seven-day-old total. Tests of that
rule do not prove that the full aggregation audit was available at each
historical forecast date.

## Output files

| File | Purpose |
|---|---|
| data/processed/sales_clean.csv | Valid transaction lines |
| data/processed/sales_rejected.csv | Original rejected records with reasons |
| reports/cleaning_report.json | Cleaning counts and repairs |
| data/processed/daily_sales.csv | Daily units and uncertainty status |
| reports/baseline/predictions.csv | Actuals, predictions, source dates, scoring flags, and errors |
| reports/baseline/per_product_metrics.csv | Per-product MAE and coverage |
| reports/baseline/metrics.json | Overall MAE, coverage, and evaluation description |

## Tests and verification

```powershell
python -m pytest -q
```

Current result: 35 tests passed in the development environment.

Tests cover:

- Valid sales and expected sample cleaning results.
- Duplicates and conflicting line IDs.
- Missing, invalid, negative, fractional, and non-finite values.
- Catalogue metadata repairs.
- Missing columns, empty files, and missing files.
- Cleaning command-line error messages.
- Daily aggregation and supported zero filling.
- Rejected records making partial totals unknown.
- Exact weekly prediction values and expected MAE.
- Unknown historical values and unknown actual totals.
- Duplicate daily rows and calendar gaps.
- Earlier predictions remaining unchanged when later daily values change
  or future days are appended.

All 35 tests passed on Python 3.10.11 and Python 3.14.
The cleaning, daily aggregation, and baseline scripts were also verified
in a fresh Python 3.10 environment and reproduced the tracked outputs.
The baseline's missing-file check returned a clear error, exit code 1,
and no traceback.

## Error handling

The cleaning command reports recognized input errors with a plain message
and nonzero exit status. Invalid individual records are saved separately.

If no usable sales remain, the cleaner writes its outputs and exits with
an explanatory error.

The baseline rejects missing required columns, empty data, invalid dates,
missing product IDs, duplicate product-date rows, calendar gaps, invalid
known totals, and unrecognized statuses. It also rejects inputs with fewer
than eight days per product or no evaluable forecasts.

Example cleaning failure check:

```powershell
python src/clean_data.py --input data/raw/does_not_exist.csv
```

Expected: a clear file-not-found message and no Python traceback.

Example baseline failure check:

```powershell
python src/baseline.py --input data/processed/does_not_exist.csv
```

Expected: a clear file-not-found message and nonzero exit status.

The aggregation script currently expects Task 1's generated input schema;
its input validation is less comprehensive than the cleaner's and
baseline's validation.

## Limitations and remaining work

- Synthetic data demonstrates functionality, not real-world accuracy.
- Real client data has not been supplied.
- Returns, multiple stores, inventory availability, and stockouts are
  outside the current sample.
- Missing records do not automatically imply zero sales in real data.
- Conservative uncertainty rules prevent scoring three products.
- Outlier detection has not been implemented.
- Python compatibility beyond the tested environment remains unverified.
- The baseline currently evaluates historical one-day forecasts; it does
  not yet provide a separate future-date forecasting command.
- Improved model tuning, broader backtesting, API/container packaging,
  and the final model card and handover belong to later tasks.