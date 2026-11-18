# VoltMart Electronics Demand Forecasting

A project to forecast daily electronics sales and support stock planning.

## Project status

- Task 1: Sales data cleaning pipeline — accepted.
- Task 2: Daily aggregation and weekly seasonal naive baseline — accepted.
- Task 3: Improved model with tuning — implemented and verified;
  awaiting submission and review.

## Data source

The dataset is synthetic, not actual VoltMart client data.

It represents one electronics store from 1 May to 31 October 2026,
with 12 products. Prices are in Pakistani rupees (PKR).

Product prices, weekend activity, and growth patterns are illustrative
assumptions, not findings about VoltMart's actual customers.

See [data/README.md](data/README.md) for the schema and deliberately
introduced errors.

## Requirements

- Python 3.10 or newer.
- Previously verified on Python 3.10.11 and Python 3.14.
- Intermediate Python versions have not been individually tested.
- Commands below use Windows PowerShell.

requirements.txt contains dependency ranges for compatible installation.
requirements-py310.txt and requirements-py314.txt preserve dependency
versions from the corresponding environments.

Recorded Task 3 model results were generated using Python 3.14 and
Scikit-learn 1.9.1. Identical fitted results across different library
versions are not guaranteed.

## Setup

Clone the repository and enter its root folder:

```powershell
git clone https://github.com/mishmaa/voltmart-demand-forecasting.git
cd voltmart-demand-forecasting
```

Create and activate an environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

To install the recorded Python 3.14 dependency versions instead:

```powershell
python -m pip install -r requirements-py314.txt
```

For the Python 3.10 dependency snapshot, use requirements-py310.txt in a
Python 3.10 environment.

If PowerShell blocks activation, use the environment's interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The same interpreter can run scripts and tests without activation.

## Run the complete workflow

Run from the repository root:

```powershell
python src/generate_sample_data.py
python src/clean_data.py
python src/build_daily_sales.py
python src/baseline.py
python src/features.py
python src/tune_model.py
python src/evaluate_model.py
python -m pytest -q
```

The generator uses seed 42 and overwrites the synthetic raw sample.
Other scripts overwrite their respective output files.

The tuning command selects settings using September only.
The final evaluation reads those settings and scores October.
Reproduction runs do not justify changing settings in response to
October's results.

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
    model_features.csv
reports/
  cleaning_report.json
  baseline/
    predictions.csv
    per_product_metrics.csv
    metrics.json
  tuning/
    search_results.csv
    selection.json
    validation_predictions.csv
  improved_model/
    predictions.csv
    per_product_metrics.csv
    metrics.json
src/
  generate_sample_data.py
  clean_data.py
  build_daily_sales.py
  baseline.py
  features.py
  tune_model.py
  evaluate_model.py
tests/
  test_clean_data.py
  test_baseline.py
  test_features.py
  test_tune_model.py
  test_evaluate_model.py
README.md
requirements.txt
requirements-py310.txt
requirements-py314.txt
.gitignore
```

## Task 1: Data cleaning pipeline

The pipeline validates transaction lines, repairs supported metadata
issues, separates unusable records, and produces a quality report.

### Run

```powershell
python src/clean_data.py
```

### Cleaning rules

- Require all eight sales columns.
- Trim surrounding whitespace and treat blank strings as missing.
- Remove exact duplicates after whitespace normalization.
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

Transaction prices may differ from catalogue reference prices.

Exact duplicates are counted and removed; they are not included in the
rejected-record file.

### Cleaning decisions and trade-offs

#### Reject missing quantities and prices

Missing transaction values are not filled using a dataset-wide average.
This avoids inventing sales values and using future observations to
repair earlier transactions.

Trade-off: rejecting records loses usable information. Aggregating only
the remaining rows could understate sales, so affected daily totals are
marked unknown during aggregation.

#### Restore descriptive metadata from the catalogue

Missing names and categories are restored using product IDs and the
fixed synthetic catalogue.

Trade-off: this assumes the catalogue is correct. Real changing
catalogues may require historical versions and effective dates.

#### Reject conflicting line IDs

After exact duplicates are removed, all remaining records sharing a line
ID are rejected instead of choosing one arbitrarily.

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

Daily units are the sum of transaction quantities, not the number of
transaction rows. Sales may underestimate demand during stockouts;
inventory availability is not represented in this sample.

### Daily aggregation

```powershell
python src/build_daily_sales.py
```

The script reads clean sales, rejected records, raw sales, and the
catalogue. It creates one row per date and product across the date
range found in valid raw dates.

The sample contains 184 days and 12 products: 2,208 daily rows.

| Column | Meaning |
|---|---|
| date | Calendar date |
| product_id | Product identifier |
| daily_units | Units sold, or an empty value when unknown |
| status | observed, assumed_zero, or unknown |

### Missing-data assumption and trade-off

Retain all 12 products.

Under the synthetic generator's complete-recording assumption, absent
product-days represent zero sales only where rejected records do not
introduce uncertainty.

- observed: sum of valid quantities, with no identified uncertainty.
- assumed_zero: no sales recorded and no identified uncertainty.
- unknown: rejected records make the total uncertain, even if some
  valid sales remain.

For a rejected record with an invalid date, another raw line from the
same transaction is used only when it supplies one unambiguous date.
This relies on the synthetic rule that transaction lines share a date.

If the date remains unresolved, the affected product's entire period
is marked unknown. An unknown product ID with a valid date makes all
products uncertain on that date. If neither can be located, the entire
table is marked uncertain.

Trade-off: conservative masking avoids false zeros and incomplete
totals, but reduces evaluation coverage. Real data requires evidence
of complete recording before absent sales can be treated as zero.

| Daily status | Product-days |
|---|---:|
| observed | 1,221 |
| assumed_zero | 385 |
| unknown | 602 |
| Total | 2,208 |

### Baseline method and reason

Use a weekly seasonal naive forecast:

```text
Prediction for product P on day D =
units sold by product P exactly seven calendar days earlier
```

Bluetooth Speaker sold 3 units on 1 May 2026, so its prediction for
8 May 2026 is 3 units.

This provides a simple benchmark for the weekly pattern built into the
synthetic sample. It has no fitted parameters.

### Baseline decisions and trade-offs

#### Choose a seven-day lag

I chose a seven-day lag because it preserves the same-weekday sales
pattern and gives us a simple benchmark. The trade-off is that it relies
on one past observation, so an unusual sales day can distort the following
week's forecast. A longer-window mean would smooth random variation but
could blur weekday differences; averaging several matching weekdays would
preserve that pattern but require more history.

#### Leave unknown lag values unavailable

An unknown seven-day-old total produces no prediction rather than a
substituted zero or average.

Trade-off: fewer predictions are available, but historical sales values
are not invented.

#### Report MAE alongside coverage

MAE uses rows where both prediction and actual are known. Coverage and
per-product results make excluded observations visible.

Trade-off: the score describes evaluated rows and may not represent
excluded products or uncertain days.

### Run the baseline

```powershell
python src/build_daily_sales.py
python src/baseline.py
```

To select another daily input:

```powershell
python src/baseline.py --input data/processed/daily_sales.csv
```

### Walk-forward evaluation

Evaluation advances one day at a time. Each prediction uses the value
from exactly seven calendar days earlier, not seven transaction rows.

The first seven days per product are warm-up. Earlier actual observations
can become history for later one-day predictions.

A prediction needs a known lag value; scoring also needs a known actual.
Unknown actuals are excluded from scoring. Unknown values on other dates
do not automatically prevent a prediction.

The baseline requires no refitting because it has no learned parameters.

### Score: mean absolute error

```text
MAE = sum of |actual - prediction| / number of scored product-days
```

MAE is measured in units and gives equal weight to each scored
product-day. Coverage is reported alongside it.

### Current baseline results

| Measure | Result |
|---|---:|
| Eligible product-days after warm-up | 2,124 |
| Available predictions | 1,545 |
| Scored product-days | 1,497 |
| Scoring coverage | 70.48% |
| Overall MAE | Approximately 1.966 units |
| Products with scored forecasts | 9 of 12 |

Three products (PRD-001, PRD-008, PRD-009) are excluded from MAE because each has an unresolved invalid-date sale, so their history is treated as unknown.

These products are:

- PRD-001: Wireless Mouse.
- PRD-008: 27-inch LED Monitor.
- PRD-009: 8GB DDR4 RAM.

Their MAE is unavailable, not zero. They remain visible in the daily
table and per-product report.

The overall score describes only evaluated synthetic product-days.

## Task 3: Improved model with tuning

### Method

A RandomForestRegressor predicts daily units using:

- Product ID, encoded inside the fitted training pipeline.
- Weekday, month, and days since the sample began.
- Sales exactly 1, 7, and 14 days earlier.
- Mean sales over the preceding seven days.

Rolling calculations are shifted before averaging, so today's target
does not enter today's features. Unknown values remain unknown.

Prediction readiness depends on available features, not on whether
today's actual sales are known.

### Training, validation, and test dates

| Stage | Dates | Purpose |
|---|---|---|
| Training | 1 May–31 August 2026 | Fit candidate models |
| Validation | 1–30 September 2026 | Select settings |
| Refit | 1 May–30 September 2026 | Fit selected settings |
| Final evaluation | 1–31 October 2026 | Compare model and baseline |

October was excluded from Task 3 tuning. It appeared in earlier Task 2
baseline analysis, so it is not a completely unseen project dataset.

The model remains fixed during each evaluation window. Earlier actuals
within the window may become historical features for later predictions;
they are not used to refit the model within that window.

### Predefined tuning search

Nine combinations were evaluated on identical September rows:

- min_samples_leaf: 2, 5, 10.
- max_depth: 3, 6, unlimited.
- n_estimators: 200, fixed.
- random_state: 42, fixed.
- n_jobs: 1 for sequential execution.
- Other estimator settings: library defaults.

Selection uses the lowest September MAE. Exact ties prefer shallower
trees, then larger leaves.

Selected settings:

- max_depth: unlimited.
- min_samples_leaf: 10.
- n_estimators: 200.
- random_state: 42.

The selection was committed before October evaluation and was not
changed in response to its results.

### Improved model decisions and trade-offs

#### Use a Random Forest with controlled leaf size

The model can learn nonlinear relationships between products, calendar
information, and recent sales. Larger leaves smooth observations while
deeper trees allow more detailed relationships.

Trade-off: flexible trees may overfit this small synthetic dataset.
Chronological validation supports selection but does not establish
real-world generalization.

#### Require known historical features

Training and scoring require all selected features. Unknown sales are
not replaced with zeros or averages.

The 28-day mean was removed before model tuning because its complete
history requirement left only 244 training rows. The revised feature
set provides 715 training rows.

Trade-off: avoiding invented history reduces usable rows and coverage.

#### Separate tuning from final evaluation

Settings are chosen using September. The selected model is then refitted
on May–September before October evaluation.

Trade-off: one validation month provides limited evidence of performance
across different seasons. Broader temporal backtesting belongs to Task 4.

#### Compare methods on matching rows

Both methods are scored on exactly the same October product-days.

Trade-off: this supports a fair comparison on the evaluated subset,
but does not measure improvement where model features are unavailable.

### Run and check

```powershell
python src/features.py
python src/tune_model.py
python src/evaluate_model.py
python -m pytest -q
```

The tuning script reconstructs features from daily sales through September.
The evaluation script reconstructs features with historical context,
reads the saved selection, and evaluates October.

model_features.csv is an inspection artifact; training scripts rebuild
features from daily_sales.csv rather than trusting a precomputed feature
file.

Output reports are overwritten when commands run. Use the recorded
dependency snapshot when reproducing the reported model results.

### Validation results

| Measure | Result |
|---|---:|
| Training rows | 715 |
| Matched September rows | 254 |
| September coverage | 70.56% |
| Selected model MAE | 1.469 units |
| Baseline MAE on matching rows | 2.189 units |

Validation scores were used for selection and are not final
generalization estimates.

### October evaluation results

| Measure | Result |
|---|---:|
| May–September refit rows | 969 |
| Total October product-days | 372 |
| Model predictions available | 199 |
| Matched scored product-days | 188 |
| Matched scoring coverage | 50.54% |
| Products scored | 9 of 12 |
| Random Forest MAE | 1.517 units |
| Seasonal naive MAE on matching rows | 1.878 units |
| Relative MAE reduction | 19.21% |

Coverage is 50.54% because only 188 of 372 October product-days have
both usable model features and known actual totals. PRD-001, PRD-008,
and PRD-009 have no scored rows because unresolved invalid-date sales
cause their entire histories to be marked unknown, making their lag
features unavailable. The other products also lose days where required
historical values or actual totals are unknown. The 19.21% MAE reduction
applies only to the matched scored rows.

The excluded products are Wireless Mouse (PRD-001), 27-inch LED Monitor
(PRD-008), and 8GB DDR4 RAM (PRD-009).

The October baseline score differs from Task 2's overall result because
the date range and scored rows differ. Task 3 coverage is also lower
because the model requires more historical values than the baseline.

These results do not establish improvement across all products or
unobserved days.

## Output files

| File | Purpose |
|---|---|
| data/processed/sales_clean.csv | Valid transaction lines |
| data/processed/sales_rejected.csv | Original rejected records and reasons |
| reports/cleaning_report.json | Cleaning counts and repairs |
| data/processed/daily_sales.csv | Daily units and uncertainty status |
| data/processed/model_features.csv | Inspectable past-only features |
| reports/baseline/predictions.csv | Baseline predictions and errors |
| reports/baseline/per_product_metrics.csv | Baseline per-product MAE and coverage |
| reports/baseline/metrics.json | Overall baseline results |
| reports/tuning/search_results.csv | All nine candidate validation scores |
| reports/tuning/selection.json | Selected settings and validation metadata |
| reports/tuning/validation_predictions.csv | Matching September predictions |
| reports/improved_model/predictions.csv | October predictions and scoring flags |
| reports/improved_model/per_product_metrics.csv | October per-product comparisons |
| reports/improved_model/metrics.json | October MAE, coverage, and limitations |

## Tests and verification

```powershell
python -m pytest -q
```

The current 55-test suite passed on Python 3.14. The preceding 54-test
suite also passed on Python 3.10.

The additional test verifies that an unseen product with prediction-ready
October features is rejected because it has no usable refit history.

Tests cover:

- Valid records, duplicates, and conflicting line IDs.
- Missing, invalid, fractional, negative, and non-finite values.
- Catalogue repairs and expected cleaning results.
- Missing columns, empty files, and missing files.
- Daily aggregation and incomplete totals.
- Exact baseline predictions and MAE.
- Unknown historical values and actual totals.
- Calendar gaps and duplicate product-date rows.
- Exact feature values and separation of product histories.
- Today's and future sales not changing today's features.
- October target changes not changing tuning selection.
- Model fitting restricted to the specified training dates.
- Matching-row model and baseline scoring.
- Rejection of unseen prediction-ready products.

The cleaning, aggregation, and baseline scripts were verified in a
separate Python 3.10 environment and reproduced their tracked outputs.

The baseline, tuning, and evaluation commands were manually checked
with nonexistent input paths. Each displayed a plain error, exited with
code 1, and showed no traceback.

Recorded Task 3 tuning and final evaluation reports were generated on
Python 3.14 with Scikit-learn 1.9.1. Identical fitted results across
versions are not claimed.

## Error handling

The cleaner reports recognized input errors with a plain message and
nonzero exit status. Invalid individual records are saved separately.

If no usable sales remain, it writes outputs and exits with an
explanatory error.

The baseline validates required columns, dates, product IDs, statuses,
daily values, duplicate rows, calendar completeness, and minimum history.
Inputs with no evaluable forecasts receive a clear error.

Feature construction validates daily values, statuses, calendar rows,
and product IDs. Tuning rejects missing usable training or validation
data. Evaluation checks selection metadata, settings, feature columns,
and the availability of matching test rows.

### Unseen products

For prediction-ready October rows, evaluate_model.py checks that each
product appeared in the usable May–September refit data. An unseen
product stops evaluation with a clear error naming its ID and exit code 1,
rather than receiving an unsupported prediction.

Rows without sufficient historical features remain unavailable.

Trade-off: rejecting unseen products prevents unsupported predictions,
but means new products need a separately designed cold-start strategy.

### Empty input and selection files

The evaluation CLI catches ValueError and OSError and exits with a plain
error message and code 1. This covers empty CSV files, missing input files,
missing October rows, missing selection files, malformed JSON, and the
explicit selection validation checks.

Malformed JSON raises JSONDecodeError, a subclass of ValueError.
An empty CSV raises pandas EmptyDataError, also a subclass of ValueError.

Example failure checks:

```powershell
python src/clean_data.py --input data/raw/does_not_exist.csv
python src/baseline.py --input data/processed/does_not_exist.csv
python src/tune_model.py --input data/processed/does_not_exist.csv
python src/evaluate_model.py --input data/processed/does_not_exist.csv
```

Each command should report an error and exit with code 1.
Check the code immediately after a command:

```powershell
$LASTEXITCODE
```

The aggregation script expects Task 1's generated input schema.
Its validation is less comprehensive than the cleaner's and baseline's.

## Evaluation limitations

The daily table uses a full-dataset quality audit, including transaction
date recovery and conservative uncertainty flags.

Evaluation is retrospective on a fixed audited dataset. Record arrival
timestamps are unavailable, so it does not reproduce historical
availability of corrections or quality flags.

Forecast features use earlier sales only. The tests do not establish
that every full-dataset quality flag was available at each historical
forecast date.

Synthetic data and limited coverage prevent claims about production
forecasting accuracy.

## Remaining work

- Broader temporal backtesting in Task 4.
- API and container packaging in Task 5.
- Model card, screenshots, demo, and handover in Task 6.
- A serialized deployment model; the current evaluation refits when run.
- A separate future-date forecasting interface.
- Real client data and evidence of recording completeness.
- Optional outlier analysis.

Returns, multiple stores, inventory availability, promotions, and
stockout effects remain outside the current sample.