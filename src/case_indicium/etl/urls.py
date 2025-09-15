from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from case_indicium.utils.ckan import get_latest_2025_csv_url

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
