import pandas as pd
import requests
from functools import lru_cache

raw_funding = pd.read_csv('algo_wiki_simple.csv', low_memory=False)
raw_funding['Year'] = pd.to_numeric(raw_funding['Year'], errors='coerce').astype('Int64')

CURRENCY_TO_WB_COUNTRY = {
    'USD': 'USA',
    'AUD': 'AUS',
    'CAD': 'CAN',
    'CHF': 'CHE',
    'CLP': 'CHL',
    'CNY': 'CHN',
    'EUR': 'EMU',
    'GBP': 'GBR',
    'JPY': 'JPN',
}

failed_lookups = []

@lru_cache(maxsize=None)
def get_rate_to_usd(currency, year):
    if currency == 'USD':
        return 1.0
    year = int(year)
    date_str = f"{year}-07-01"
    url = f"https://api.frankfurter.app/{date_str}"
    params = {"from": currency, "to": "USD"}
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        failed_lookups.append((currency, year, f"HTTP {resp.status_code}"))
        return None
    data = resp.json()
    rate = data.get("rates", {}).get("USD")
    if rate is None:
        failed_lookups.append((currency, year, "no rate returned"))
        return None
    return rate

def compute_total_funding(row):
    total = 0
    has_data = False
    for i in range(16):
        curr_col = f'openalex_currency_{i}'
        amt_col = f'openalex_amount_{i}'
        pub_col = f'openalex_publications_{i}'
        if curr_col not in row or amt_col not in row or pub_col not in row:
            continue
        currency = row[curr_col]
        amount = row[amt_col]
        pubs = row[pub_col]
        year = row['Year']
        if pd.isna(currency) or pd.isna(amount) or pd.isna(year):
            continue
        rate = get_rate_to_usd(currency, year)
        if rate is None:
            continue
        usd_amount = amount * rate
        has_data = True
        if pd.isna(pubs) or pubs <= 1:
            total += usd_amount
        else:
            total += usd_amount / pubs
    return total if has_data else None

raw_funding['total_funding'] = raw_funding.apply(compute_total_funding, axis=1)
raw_funding['total_funding'] = raw_funding['total_funding'].round(0).astype('Int64')