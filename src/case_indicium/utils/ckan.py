from __future__ import annotations

import requests

CKAN_API = "https://opendatasus.saude.gov.br/api/3/action/package_show"
# The current public package id for SRAG dataset that contains 2019–2025 resources:
PACKAGE_ID = "srag-2021-a-2024"


def get_latest_2025_csv_url(package_id: str = PACKAGE_ID, timeout: float = 30.0) -> str:
    """Return the latest CSV URL for the '2025 - Banco vivo' SRAG resource on OpenDataSUS.

    This function queries the CKAN API for the given package and finds the CSV
    resource whose name contains '2025' and 'Banco vivo' (case-insensitive).

    Args:
        package_id: CKAN package identifier (slug or UUID).
        timeout: HTTP timeout in seconds for the CKAN API request.

    Returns:
        The absolute URL of the latest 2025 CSV resource.

    Raises:
        requests.HTTPError: If the HTTP call fails.
        RuntimeError: If the CKAN response indicates failure or no matching resource is found.
    """
    resp = requests.get(CKAN_API, params={"id": package_id}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError("CKAN API returned success=false.")

    for res in payload["result"]["resources"]:
        name = (res.get("name") or "").lower()
        fmt = (res.get("format") or "").upper()
        if "2025" in name and "banco vivo" in name and fmt == "CSV":
            return res["url"]

    raise RuntimeError("CSV resource for 2025 'Banco vivo' not found on CKAN.")
