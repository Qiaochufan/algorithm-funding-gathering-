import os
import base64
import json
import pandas as pd
from pathlib import Path
from openai import OpenAI
from docx import Document
import time
import random
PDF_FOLDER  = "test"        
CSV_PATH    = "source.csv"   
PROMPT_PATH = "find_funder_prompt.txt"

API_KEY     =""
MODEL       = "gpt-4o"
def load_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")

SYSTEM_PROMPT = load_prompt(PROMPT_PATH)

import time
import random

def extract_funders(client: OpenAI, pdf_path: str, retries: int = 5) -> dict:
    with open(pdf_path, "rb") as f:
        uploaded = client.files.create(file=f, purpose="user_data")

    try:
        for attempt in range(retries):
            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        f"Extract the funder information from this paper: {Path(pdf_path).name}\n"
                                        "If no funding information is found, return exactly: {}"
                                    )
                                },
                                {
                                    "type": "file",
                                    "file": {"file_id": uploaded.id}
                                }
                            ]
                        }
                    ],
                    max_tokens=1000,
                    temperature=0,
                )
                break  # success, exit retry loop

            except Exception as e:
                if "429" in str(e):
                    wait = 2 ** attempt + random.uniform(0, 1)  # exponential backoff
                    print(f"\n  [rate limit] waiting {wait:.1f}s before retry {attempt+1}/{retries}")
                    time.sleep(wait)
                    if attempt == retries - 1:
                        raise  # out of retries
                else:
                    raise  # non-rate-limit error, don't retry
    finally:
        client.files.delete(uploaded.id)

    raw = response.choices[0].message.content.strip()
    print(f"\n  [raw response]: {raw[:200]}")

    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    if not raw or raw.lower() == "not found":
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [could not parse JSON]: {raw[:200]}")
        return {}

def flatten_to_csv_columns(funder_dict: dict) -> tuple[str, str]:
    n = sum(1 for k in funder_dict if k.startswith("funder_"))
    funders, awards = [], []
    for i in range(1, n + 1):
        funders.append(funder_dict.get(f"funder_{i}", ""))
        awards.append(funder_dict.get(f"award_id_{i}", ""))
    return "; ".join(funders), "; ".join(awards)


def main():
    client = OpenAI(api_key=API_KEY)

    df = pd.read_csv(CSV_PATH)
    # Explicitly set object dtype to avoid float64 assignment errors
    if "funders" not in df.columns:
        df["funders"] = pd.Series(dtype="object")
    else:
        df["funders"] = df["funders"].astype(object)
    if "award_id" not in df.columns:
        df["award_id"] = pd.Series(dtype="object")
    else:
        df["award_id"] = df["award_id"].astype(object)

    pdf_files = sorted(Path(PDF_FOLDER).glob("*.pdf"), key=lambda p: int(p.stem))
    if not pdf_files:
        print(f"No PDFs found in {PDF_FOLDER}")
        return

    for pdf_path in pdf_files:
        try:
            row_num = int(pdf_path.stem)
        except ValueError:
            print(f"Skipping {pdf_path.name} — filename is not a number")
            continue

        print(f"Processing {pdf_path.name} ...", end=" ", flush=True)
        try:
            funder_dict = extract_funders(client, str(pdf_path))
            funders_str, awards_str = flatten_to_csv_columns(funder_dict)
            df.at[row_num, "funders"]  = funders_str
            df.at[row_num, "award_id"] = awards_str
            print(f"funders: {funders_str[:60]}")
        except Exception as e:
            print(f"ERROR: {e}")
            df.at[row_num, "funders"]  = "error"
            df.at[row_num, "award_id"] = str(e)

        df.to_csv("result.csv", index=False)
        time.sleep(3)  

    print("Done. Results saved to result.csv")


if __name__ == "__main__":
    main()