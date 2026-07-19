"""IRA Settings Manager — Persistent user settings with Nominatim reverse geocoding."""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
import urllib.parse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(ROOT_DIR, "ira_settings.json")

DEFAULT_SETTINGS = {
    "location": {
        "auto_detect": True,
        "lat": 18.3972,
        "lng": 76.5678,
        "city": "Latur, IN",
        "full_address": "",
        "street": "",
        "landmark": "",
        "last_detected": None,
    },
    "search": {
        "engines": ["google", "tavily", "ddg", "wiki", "reddit"],
        "max_results": 5,
    },
    "maps": {
        "auto_open": True,
        "default_zoom": 14,
    },
    "gestures": {
        "enabled": False,
        "system_control": True,   # real OS cursor control (fist engage / pinch click / palm scroll)
        "smoothing": 0.7,         # 0 = raw, 1 = very smooth (tunes One Euro min_cutoff)
        "skeleton": True,         # draw neon hand skeleton on camera preview
    },
    "screenshots": {
        "auto_screenshot": True,
    },
    "reasoning": {
        "enabled": True,
        "level": "high",
    },
    "avatar": {
        "enabled": True,
    },
}


# ═══════════════════════════════════════════════════════════════
#  NOMINATIM REVERSE GEOCODING (Free, no key)
# ═══════════════════════════════════════════════════════════════

def reverse_geocode(lat: float, lng: float) -> dict:
    """Convert coordinates to full address using Nominatim (OpenStreetMap).
    
    Returns: {full_address, street, city, state, landmark, postcode}
    """
    try:
        params = urllib.parse.urlencode({
            "lat": lat,
            "lon": lng,
            "format": "json",
            "addressdetails": 1,
            "accept-language": "en",
        })
        url = f"https://nominatim.openstreetmap.org/reverse?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "IRA/2.0 (desktop-ai-agent)",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        addr = data.get("address", {})
        display = data.get("display_name", "")

        # Extract components
        road = addr.get("road", "")
        house_number = addr.get("house_number", "")
        suburb = addr.get("suburb", addr.get("neighbourhood", ""))
        city = addr.get("city", addr.get("town", addr.get("village", "")))
        state = addr.get("state", "")
        postcode = addr.get("postcode", "")
        landmark = addr.get("amenity", addr.get("tourism", addr.get("shop", "")))

        # Build street
        street = road
        if house_number:
            street = f"{house_number}, {road}" if road else house_number

        # Build short address
        parts = []
        if suburb:
            parts.append(suburb)
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if postcode:
            parts.append(postcode)
        short_address = ", ".join(parts) if parts else display.split(",")[0] if display else "Unknown"

        return {
            "full_address": display,
            "street": street,
            "city": city or short_address,
            "state": state,
            "landmark": landmark,
            "postcode": postcode,
            "short_address": short_address,
        }

    except Exception as e:
        print(f"[SETTINGS] Reverse geocode failed: {e}")
        return {
            "full_address": "",
            "street": "",
            "city": "",
            "state": "",
            "landmark": "",
            "postcode": "",
            "short_address": "",
        }


# ═══════════════════════════════════════════════════════════════
#  IP GEOLOCATION
# ═══════════════════════════════════════════════════════════════

def _ip_geolocation() -> dict:
    """Get rough coords from IP (city-level ~50km accuracy)."""
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "IRA/2.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        loc = data.get("loc", "")
        city = data.get("city", "Unknown")
        country = data.get("country", "")

        if loc and "," in loc:
            lat_str, lng_str = loc.split(",", 1)
            return {
                "lat": float(lat_str.strip()),
                "lng": float(lng_str.strip()),
                "city": f"{city}, {country}" if country else city,
            }

    except Exception as e:
        print(f"[SETTINGS] IP geolocation failed: {e}")

    return {
        "lat": DEFAULT_SETTINGS["location"]["lat"],
        "lng": DEFAULT_SETTINGS["location"]["lng"],
        "city": DEFAULT_SETTINGS["location"]["city"],
    }


# ═══════════════════════════════════════════════════════════════
#  MAIN DETECTION FUNCTION
# ═══════════════════════════════════════════════════════════════

def detect_location() -> dict:
    """Detect user location with full address via IP + Nominatim reverse geocode.
    
    Flow: IP detection → get rough coords → Nominatim reverse geocode → full address
    """
    # Step 1: Get rough coords from IP
    ip_data = _ip_geolocation()
    lat, lng = ip_data["lat"], ip_data["lng"]
    city = ip_data["city"]

    print(f"[SETTINGS] IP location: {city} ({lat}, {lng})")

    # Step 2: Reverse geocode to get full address
    geo = reverse_geocode(lat, lng)

    full_address = geo.get("full_address", "")
    street = geo.get("street", "")
    landmark = geo.get("landmark", "")
    short_addr = geo.get("short_address", city)

    if full_address:
        print(f"[SETTINGS] Full address: {full_address[:80]}...")

    return {
        "lat": lat,
        "lng": lng,
        "city": short_addr or city,
        "full_address": full_address,
        "street": street,
        "landmark": landmark,
        "last_detected": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ═══════════════════════════════════════════════════════════════
#  SETTINGS PERSISTENCE
# ═══════════════════════════════════════════════════════════════

def load_settings() -> dict:
    """Load settings from disk. Auto-detects location if stale (>24h)."""
    settings = None

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass

    if not settings:
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy

    # Ensure all keys exist (migration-safe)
    settings.setdefault("location", dict(DEFAULT_SETTINGS["location"]))
    settings.setdefault("search", dict(DEFAULT_SETTINGS["search"]))
    settings.setdefault("maps", dict(DEFAULT_SETTINGS["maps"]))
    settings.setdefault("gestures", dict(DEFAULT_SETTINGS["gestures"]))
    settings.setdefault("reasoning", dict(DEFAULT_SETTINGS["reasoning"]))
    settings.setdefault("avatar", dict(DEFAULT_SETTINGS["avatar"]))
    settings["location"].setdefault("auto_detect", True)
    settings["location"].setdefault("lat", DEFAULT_SETTINGS["location"]["lat"])
    settings["location"].setdefault("lng", DEFAULT_SETTINGS["location"]["lng"])
    settings["location"].setdefault("city", DEFAULT_SETTINGS["location"]["city"])
    settings["location"].setdefault("full_address", "")
    settings["location"].setdefault("street", "")
    settings["location"].setdefault("landmark", "")
    settings["location"].setdefault("last_detected", None)
    settings["search"].setdefault("engines", DEFAULT_SETTINGS["search"]["engines"])
    settings["search"].setdefault("max_results", 5)
    settings["maps"].setdefault("auto_open", True)
    settings["maps"].setdefault("default_zoom", 14)
    settings["gestures"].setdefault("enabled", False)
    settings["gestures"].setdefault("system_control", True)
    settings["gestures"].setdefault("smoothing", 0.7)
    settings["gestures"].setdefault("skeleton", True)
    settings["reasoning"].setdefault("enabled", True)
    settings["reasoning"].setdefault("level", "high")

    # Auto-detect if enabled and stale (>24h)
    if settings["location"].get("auto_detect"):
        last = settings["location"].get("last_detected")
        if last:
            try:
                last_ts = time.mktime(time.strptime(last, "%Y-%m-%dT%H:%M:%S"))
                age_hours = (time.time() - last_ts) / 3600
                if age_hours < 24:
                    return settings  # Still fresh
            except (ValueError, OverflowError):
                pass

        # Re-detect
        detected = detect_location()
        settings["location"]["lat"] = detected["lat"]
        settings["location"]["lng"] = detected["lng"]
        settings["location"]["city"] = detected["city"]
        settings["location"]["full_address"] = detected["full_address"]
        settings["location"]["street"] = detected["street"]
        settings["location"]["landmark"] = detected["landmark"]
        settings["location"]["last_detected"] = detected["last_detected"]
        save_settings(settings)

    return settings


def save_settings(settings: dict) -> None:
    """Persist settings to disk."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def get_user_location() -> tuple[float, float]:
    """Return (lat, lng) from current settings."""
    settings = load_settings()
    loc = settings.get("location", {})
    return (
        loc.get("lat", DEFAULT_SETTINGS["location"]["lat"]),
        loc.get("lng", DEFAULT_SETTINGS["location"]["lng"]),
    )


def get_user_city() -> str:
    """Return city/area name from current settings."""
    settings = load_settings()
    return settings.get("location", {}).get("city", DEFAULT_SETTINGS["location"]["city"])


def get_user_address() -> str:
    """Return full address from current settings."""
    settings = load_settings()
    return settings.get("location", {}).get("full_address", "")


def get_user_street() -> str:
    """Return street name from current settings."""
    settings = load_settings()
    return settings.get("location", {}).get("street", "")


def get_maps_settings() -> dict:
    """Return maps settings."""
    settings = load_settings()
    return settings.get("maps", DEFAULT_SETTINGS["maps"])
