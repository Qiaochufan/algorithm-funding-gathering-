import math
import re
import time

import numpy as np
import requests
from tqdm import tqdm

API_KEY = "" 
BASE_URL = "https://api.openalex.org/awards"
SLEEP_SECONDS = 0.2   
MAX_RETRIES = 3      
REQUEST_TIMEOUT = 30  


CLEAN_PATTERNS = [
    r"[A-Za-z]",           #remove letters
    r"\([^)]*\)|[.\-/]",   #  remove symbols
    r"[.\-/A-Za-z]",       # both
]

CS_KEYWORDS = [
    "algorithm", "algorithms", "computer science", "computing",
    "computation", "computational", "software", "computer engineering",
    "artificial intelligence", "machine learning", "data structure"
]



def _is_missing(value) -> bool:
    """True for NaN / None / empty-string values."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, str) and value.strip().lower() == "nan":
        return True
    return False

#search awards
def _search_awards(funder_award_id: str, api_key: str | None) -> list[dict]:
    
    params = {"filter": f"funder_award_id:{funder_award_id}"}
    if api_key:
        params["api_key"] = api_key

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except requests.exceptions.RequestException:
            if attempt == MAX_RETRIES - 1:
                return []
            time.sleep(1.0 * (attempt + 1))
    return []


def _looks_cs_related(award: dict) -> bool:
    text = " ".join(
        filter(None, [award.get("display_name"), award.get("description")])
    ).lower()
    return any(keyword in text for keyword in CS_KEYWORDS)

#determine which award is related to cs
def _pick_best_award(results: list[dict]) -> dict | None:
    if not results:
        return None
    if len(results) == 1:
        return results[0]

    cs_matches = [r for r in results if _looks_cs_related(r)]
    if cs_matches:
        return cs_matches[0]

    return results[0]

#remove url in the id
def _short_id(award: dict) -> str:
    return award["id"].rsplit("/", 1)[-1]


#main function
def get_openalex_award_ids(
    raw_award_ids: np.ndarray,
    api_key: str | None = API_KEY,
) -> list[dict]:

    output = []
    valid_ids = [rid for rid in raw_award_ids if not _is_missing(rid)]

    for raw_id in tqdm(valid_ids, desc="Matching award IDs"):
        raw_id_str = str(raw_id).strip()

    #direct search
        results = _search_awards(raw_id_str, api_key)
        matched_award = _pick_best_award(results)
        time.sleep(SLEEP_SECONDS)

    #apply modifer
        if matched_award is None:
            for pattern in CLEAN_PATTERNS:
                cleaned = re.sub(pattern, "", raw_id_str).strip()
                if not cleaned or cleaned == raw_id_str:
                    continue
                results = _search_awards(cleaned, api_key)
                matched_award = _pick_best_award(results)
                time.sleep(SLEEP_SECONDS)
                if matched_award is not None:
                    break

        output.append({
            "raw_award": raw_id,
            "openalex_award_id": _short_id(matched_award) if matched_award else np.nan,
        })

    return output



if __name__ == "__main__":
    import pandas as pd

    input_df = pd.read_csv("raw_award_ids.csv")
    matched = get_openalex_award_ids(input_df["raw_award_id"].to_numpy(), api_key=API_KEY)
    output_df = pd.DataFrame(matched)
    output_df.to_csv("openalex_award_id_matched.csv", index=False)
    print("finished")
