# Sales Data Specification

## Source

Synthetic electronics-store sales data created for development and testing.
This is not actual VoltMart client data.

## Scope

One store, with sales transactions only.
Returns, inventory availability, and stockouts are outside this sample.

## Row definition

Each row represents one product line in a transaction.
A transaction can contain multiple lines.
Each line_id identifies one unique sales line.

## Columns

| Column | Meaning |
|---|---|
| transaction_id | Purchase identifier |
| line_id | Unique sales-line identifier |
| date | Sale date in YYYY-MM-DD format |
| product_id | Stable product identifier |
| product_name | Product name |
| category | Electronics category |
| quantity | Positive whole number of units sold |
| unit_price | Positive price per unit in PKR |

## Forecasting target

Daily units sold per product.

## Limitations

- Missing records do not automatically mean zero sales.
- Sales may underestimate demand when products are out of stock.
- Synthetic data demonstrates functionality, not real-world accuracy.
- Raw test data will intentionally contain errors to exercise cleaning rules.

## Generate the sample

From the project root, run:

    python src/generate_sample_data.py

The generator uses seed 42 and covers May through October 2026.
It overwrites data/raw/sales_raw.csv with a reproducible sample.

The product catalogue contains illustrative PKR reference prices.
These are generation inputs, not verified market prices or mandatory
transaction prices.

The sample includes 38 deliberately affected rows:
- 5 missing quantities
- 5 missing prices
- 4 invalid dates
- 4 missing product names
- 4 negative quantities
- 4 nonnumeric quantities
- 4 zero prices
- 4 unknown product IDs
- 4 categories with surrounding whitespace

It also includes 5 exact duplicate rows and is shuffled.

Weekend activity and gradual growth are simulated assumptions,
not findings about VoltMart's actual customers.