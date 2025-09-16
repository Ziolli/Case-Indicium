from __future__ import annotations


import json
from pathlib import Path
from typing import Dict
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


def refresh_2025_url_in_manifest(manifest_path: str | Path) -> Dict[str, str]:
    """Update manifest JSON so key '2025' always points to the latest 'Banco vivo' CSV.

    This function reads the given JSON manifest mapping year->URL, replaces the
    '2025' entry with the live 'Banco vivo' URL resolved from CKAN, writes the
    updated JSON back to disk, and returns the mapping.

    Args:
        manifest_path: Path to the JSON manifest, e.g. 'data/raw/data_urls.json'.

    Returns:
        A dictionary mapping year strings (e.g., "2019") to absolute URLs.

    Raises:
        FileNotFoundError: If the manifest file does not exist.
        json.JSONDecodeError: If the manifest contents are not valid JSON.
        RuntimeError: If the CKAN lookup fails to find the 2025 CSV.
    """
    p = Path(manifest_path)
    mapping: Dict[str, str] = json.loads(p.read_text(encoding="utf-8"))

    # Always refresh 2025 to the latest live CSV
    mapping["2025"] = get_latest_2025_csv_url()

    p.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    return mapping

def load_year_url_manifest(path: Path) -> Dict[str, str]:
    """
    Load a year->url manifest (e.g., data/raw/data_urls.json).

    Args:
        path: Path to a JSON file mapping year (string) to CSV URL.

    Returns:
        Dict mapping year to url. Raises ValueError for empty manifests.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError(f"Invalid or empty manifest at {path}")
    return {str(k): str(v) for k, v in data.items()}
