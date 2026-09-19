import pandas as pd
import requests
award_data = pd.read_csv("nsf_doi.csv")

def get_award_stats(award_id: str, award_data: pd.DataFrame):
    """
    Given an NSF award ID, compute:
      1. The max publication count, comparing our own NSF data
         (award_data) against OpenAlex's funded_outputs_count.
      2. The award's total dollar amount (from our own data).
      3. The average money per publication (total_amount / publication_count).

    Parameters
    ----------
    award_id : str
        The NSF award ID to look up (e.g. "1218188").
    award_data : pd.DataFrame
        DataFrame containing "award_id" and "awd_amount" columns, where
        each row represents one publication linked to an award
        (e.g. nsf_doi.csv).

    Returns
    -------
    tuple[int, float | None, float | None]
        (publication_count, total_amount, average_money)
    """
    award_id = str(award_id)

    # 1. Count publications for this award in our own data
    #    (assumes one row per publication-award link)
    award_id_str = award_data["award_id"].astype(str)
    local_count = int((award_id_str == award_id).sum())

    # 2. Count publications for this award from OpenAlex
    openalex_count = 0
    url = "https://api.openalex.org/awards"
    params = {"filter": f"funder_award_id:{award_id},funder.id:F4320306076"}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        results = response.json().get("results", [])
        if results:
            openalex_count = results[0].get("funded_outputs_count", 0) or 0
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        print(f"OpenAlex lookup failed for award {award_id}: {e}")

    # 3. Take the max of the two publication counts
    publication_count = max(local_count, openalex_count)

    # 4. Look up the award's total dollar amount from our own data.
    #    Filter to rows matching this award_id, then take the amount
    #    from one of them (they should all be the same value, since
    #    awd_amount is per-award, not per-publication).
    matching_rows = award_data[award_id_str == award_id]
    if not matching_rows.empty:
        total_amount = matching_rows["awd_amount"].iloc[0]
    else:
        total_amount = None

    # 5. Compute the average money per publication, guarding against
    #    a zero or unknown publication count.
    if total_amount is not None and publication_count > 0:
        average_money = total_amount / publication_count
        print(f"Average money per publication for award {award_id}: {average_money:,.2f}")
    else:
        average_money = None
        print(f"Could not compute average money for award {award_id} "
              f"(total_amount={total_amount}, publication_count={publication_count})")
    return publication_count, total_amount, average_money



if __name__ == "__main__":
    count, total, avg = get_award_stats("9454173", award_data)
    print(f"we found  {count}, and total money is {total}, and average is {avg}")
    pass