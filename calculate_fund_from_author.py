import os
import time
import requests
from tqdm import tqdm

AUTHORS_URL = "https://api.openalex.org/authors"
WORKS_URL = "https://api.openalex.org/works"
AWARDS_URL = "https://api.openalex.org/awards"


api_key = ''
mail = ''


def _common_params(extra: dict = None) -> dict:
    params = dict(extra or {})
    params["api_key"] = api_key
    params["mailto"] = mail
    return params

#get author openalex id
def get_author_id(author_name: str) -> str | None:
   
    params = _common_params({"search": author_name})
    response = requests.get(AUTHORS_URL, params=params, timeout=30)
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None
    return results[0]["id"].rsplit("/", 1)[-1]


#get all papers for an author in one year
def get_all_author_works(author_id: str) -> list[dict]:
    works = []
    cursor = "*"
    while cursor:
        params = _common_params({
            "filter": f"author.id:{author_id}",
            "per-page": 200,
            "cursor": cursor,
            "select": "id,awards",
        })
        resp = requests.get(WORKS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        works.extend(results)

        cursor = data.get("meta", {}).get("next_cursor")
        if not results or not cursor:
            break

    return works

#get awards in one year
def get_unique_award_ids(works: list[dict]) -> set[str]:
    award_ids = set()
    for work in works:
        for award in work.get("awards") or []:
            award_id = award.get("id")
            if award_id:
                award_ids.add(award_id.rsplit("/", 1)[-1])
    return award_ids

#get award money
def get_award_details(award_id: str) -> dict | None:

    params = _common_params({"select": "id,amount,start_year,end_year"})
    try:
        resp = requests.get(f"{AWARDS_URL}/{award_id}", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError, KeyError):
        return None

    amount = data.get("amount")
    if amount is None:
        return None

    start_year = data.get("start_year")
    end_year = data.get("end_year")

    # If only one of the two years is known, treat it as a single-year grant.
    if start_year is None and end_year is None:
        return None
    if start_year is None:
        start_year = end_year
    if end_year is None:
        end_year = start_year
    if end_year < start_year:
        start_year, end_year = end_year, start_year

    return {
        "amount": float(amount),
        "start_year": int(start_year),
        "end_year": int(end_year),
    }


def get_author_funding_for_year(author_name: str, year: int) -> float:

    author_id = get_author_id(author_name)
    if not author_id:
        raise ValueError(f"No OpenAlex author found for '{author_name}'")

    works = get_all_author_works(author_id)
    award_ids = get_unique_award_ids(works)

    total_funding = 0.0
    for award_id in tqdm(award_ids, desc=f"Checking grants for {year}"):
        details = get_award_details(award_id)
        time.sleep(0.1) 

        if details is None:
            continue

        if details["start_year"] <= year <= details["end_year"]:
            num_years = details["end_year"] - details["start_year"] + 1
            total_funding += details["amount"] / num_years

    return round(total_funding)

if __name__ == "__main__":
    author = "Yann lecun"
    year = 2023
    funding = get_author_funding_for_year(author, year)
    print(f"{author} received approximately ${funding:,} in funding in {year}")