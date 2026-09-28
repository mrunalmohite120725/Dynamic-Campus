"""
nanonets_docstrange.py — Nanonets API extractor.
API key loaded from .env via config — never hardcoded.
"""
import requests
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


def extract_json(pdf_path: str, output_path: str = None) -> dict:
    """
    Upload a PDF to Nanonets and return the extracted JSON.
    Also saves JSON to disk at output_path (defaults to Config.JSON_OUTPUT).
    """
    if not Config.NANONETS_API_KEY:
        raise ValueError("NANONETS_API_KEY is not set in .env")

    url = Config.NANONETS_URL
    headers = {"Authorization": f"Bearer {Config.NANONETS_API_KEY}"}

    with open(pdf_path, "rb") as f:
        response = requests.post(
            url,
            headers=headers,
            files={"file": f},
            data={"output_format": "json"},
            timeout=120,
        )

    response.raise_for_status()
    result = response.json()

    # Save JSON to disk
    save_path = output_path or Config.JSON_OUTPUT
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as out:
        json.dump(result, out, indent=4)

    print(f" JSON extracted and saved to {save_path}")
    return result