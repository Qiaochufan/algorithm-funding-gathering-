import re
import csv
import requests
import pandas as pd
import time
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from tqdm import tqdm
origin = pd.read_csv("links_with_doi.csv")
missing = origin[origin["doi"].isna()]
science_api = ""
api_key = ""
ieee_api = ""
pd.set_option('display.max_colwidth', None)


def get_pii_from_url(link):
    match = re.search(r'sciencedirect\.com/science/article/pii/([A-Z0-9]+)', link, re.IGNORECASE)
    return match.group(1) if match else None

def fetch_doi_from_sciencedirect(pii):
    if not pii:
        return None
    
    url = f"https://api.elsevier.com/content/article/pii/{pii}"
    headers = {
        "X-ELS-APIKey": science_api,
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            doi = data.get('full-text-retrieval-response', {}) \
                      .get('coredata', {}) \
                      .get('prism:doi')
            if doi:
                return f"https://doi.org/{doi}"
        
        elif response.status_code == 401:
            print(f"\nInvalid API key")
        elif response.status_code == 403:
            print(f"\nAccess denied for PII {pii} — may require institutional access")
        elif response.status_code == 429:
            print(f"\nRate limit hit — sleeping 10s")
            time.sleep(10)
        else:
            print(f"\nUnexpected status {response.status_code} for PII {pii}")
    
    except Exception as e:
        print(f"\nError for PII {pii}: {e}")
    
    return None


def convert_arxiv_link(link):
    if isinstance(link, str) and '/pdf/' in link:
        link = link.replace('/pdf/', '/abs/')
        if link.endswith('.pdf'):
            link = link[:-4]
    return link
def get_doi_from_acm(acm_url):
    # handle doid= format directly
    match = re.search(r'doid=([\d.]+)', acm_url)
    if match:
        return f"10.1145/{match.group(1)}"
    
    # handle id= format by searching OpenAlex via landing page URL
    try:
        time.sleep(0.5)
        response = requests.get(
            "https://api.openalex.org/works",
            params={
                "filter": f"locations.landing_page_url:{acm_url}",
                "api_key": api_key
            }
        )
        data = response.json()
        results = data.get("results", [])
        if results:
            doi = results[0].get("doi", "")
            return doi.replace("https://doi.org/", "")
        else:
            print(f"No results for {acm_url}")
    except Exception as e:
        print(f"Error: {e}")
    
    return None
def clean_doi(doi):
    doi = doi.split("?")[0]
    doi = doi.split("#")[0]
    doi = doi.rstrip(".,;)")

    for ext in [".pdf", ".html", ".htm", ".xml"]:
        if doi.lower().endswith(ext):
            doi = doi[:-len(ext)]
    return doi
def extract_doi(url):
    if pd.isna(url):
        return None

    url = unquote(str(url))

    pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+'
    match = re.search(pattern, url, re.IGNORECASE)

    if not match:
        return None

    return clean_doi(match.group(0))
def get_arxiv_id(link):
    match = re.search(r'arxiv\.org/(?:abs|pdf)/([^\s/]+?)(?:\.pdf)?$', link, re.IGNORECASE)
    return match.group(1) if match else None

def fetch_doi_from_arxiv(arxiv_id):
    if not arxiv_id:
        return None
    
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        
        doi_el = root.find('.//arxiv:doi', ns)
        if doi_el is not None:
            return f"https://doi.org/{doi_el.text.strip()}"
        
    except Exception as e:
        print(f"\nAPI error for {arxiv_id}: {e}")
    return f"https://doi.org/10.48550/arXiv.{arxiv_id}"


#get each of the websites category
science = missing[missing['Link'].str.contains('sciencedirect', na=False)]
acm = missing[missing['Link'].str.contains('dl.acm.org', na=False)]
arx = missing[missing['Link'].str.contains('arxiv', na=False)]
ieee = missing[missing['Link'].str.contains('ieeexplore', na=False)]

tqdm.pandas()

for idx, row in tqdm(arx.iterrows(), total=len(arx), desc="Fetching DOIs"):
    link = row['Link']
    arxiv_id = get_arxiv_id(link)
    doi = fetch_doi_from_arxiv(arxiv_id)
    arx.at[idx, 'doi'] = doi
    time.sleep(3.2)
print("finished")  
arx.to_csv("indirect_doi/arx_doi.csv", index=False)

for idx, row in tqdm(science.iterrows(), total=len(science), desc="Fetching DOIs"):
    if pd.notna(row.get('doi')) and row['doi'] != '':
        continue 
    
    pii = get_pii_from_url(row['Link'])
    science.at[idx, 'doi'] = fetch_doi_from_sciencedirect(pii)
    time.sleep(1) 

science.to_csv('indirect_doi/science_doi.csv', index=False)
print("finished")

acm['doi'] = acm['Link'].apply(get_doi_from_acm)
acm.to_csv('indirect_doi/acm_doi.csv', index=False)