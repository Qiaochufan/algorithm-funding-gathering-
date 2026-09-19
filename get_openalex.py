import requests 

api_key = 'MvHLoWcEkBPLfRGmGVEbgW'

# two functions that give the funder name or award id, return its corrsponding openalex information
def get_openalex_id(funder_award_id: str, api_key: str) -> list[str]:
    url = "https://api.openalex.org/awards"
    params = {"filter": f"funder_award_id:{funder_award_id}", "api_key": api_key}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    results = data.get("results", [])
    return [r["id"].rsplit("/", 1)[-1] for r in results]

def get_openalex_funder_id(funder_name: str, api_key: str) -> str | None:
    name = funder_name.strip()
    try:
        resp = requests.get(
            "https://api.openalex.org/funders",
            params={"search": name, "api_key": api_key},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except requests.exceptions.RequestException:
        results = []
    if results:
        return results[0]["id"].rsplit("/", 1)[-1]
    return None
