# EURO 2024 Forecasting

Forecast UEFA EURO 2024 results. Firstly, historical data has to be fetched for each team in the tournament. Then,
Machine Learning models are used to predict the results.

## Structure

- `bin` - contains binary files for selenium and chromium driver
- `data` - contains team lineups and fetched historical data
- `notebooks` - contains Jupyter notebooks for with experiments

Main scraping ETL files are in the root of this project.

## Installation

```bash
pip install -r requirements.txt
./install.sh
```

## Getting started

### Fetch data

```bash
python3 fetch_data.py
```
