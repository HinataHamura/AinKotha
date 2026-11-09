"""Nearest police station lookup backed by the local thana dataset."""
import json
import math
from pathlib import Path

_DATA_FILE = Path(__file__).parent / "data" / "thanas.json"
_EARTH_RADIUS_KM = 6371.0


def load_thanas() -> list[dict]:
    with _DATA_FILE.open(encoding="utf-8") as data_file:
        thanas = json.load(data_file)
    if not isinstance(thanas, list):
        raise ValueError(f"{_DATA_FILE} must contain a JSON array")
    return thanas


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance between two coordinates in kilometers."""
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    hav = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, hav)))


def find_nearest(lat: float, lng: float, limit: int = 1) -> list[dict]:
    """Return the closest stations with their straight-line distance."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    nearby = [
        {**thana, "distance_km": haversine(lat, lng, thana["lat"], thana["lng"])}
        for thana in _THANAS
    ]
    return sorted(nearby, key=lambda thana: thana["distance_km"])[:limit]


_THANAS = load_thanas()
