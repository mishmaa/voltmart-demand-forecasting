# VoltMart Electronics Demand Forecasting

An internship project to predict electronics sales and support stock planning.

## Current stage

Task 1: Build a reusable data cleaning pipeline.

## Requirements

- Python 3.14
- Dependencies listed in requirements.txt

## Setup

Run these commands from the project folder in PowerShell:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt

## Verify the environment

    python -c "import pandas, numpy, pytest, matplotlib; print('All libraries imported successfully')"

## Project structure

- data/raw/: original sample sales data
- data/processed/: cleaned data
- src/: Python source code
- tests/: automated tests
- reports/: data quality summaries and charts

## Status

Environment setup is complete. The cleaning pipeline, sample data,
tests, and cleaning decisions will be added next.