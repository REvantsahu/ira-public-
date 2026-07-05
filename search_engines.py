"""IRA Search Engines — Multi-engine web search with Google-first priority chain."""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.parse
from itertools import cycle

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load .env if available (for standalone testing)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT_DIR, ".env"))
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════
#  GOOGLE AI STUDIO — SEARCH GROUNDING (Priority 1)
# ═══════════════════════════════════════════════════════════════

def google_search_grounding(query: str) -> str:
    """Search using Gemini's Google Search grounding — rotate ALL keys per model."""
    try:
        from google import genai
        from google.genai import types
        from key_manager import APIKeyManager
        from config import SEARCH_MODELS

        km = APIKeyManager()

        for model in SEARCH_MODELS:
            for _ in range(len(km.state["api_keys"])):
                key = km.get_key()
                if not key:
                    break
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model=model,
                        contents=query,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_search=types.GoogleSearch())],
                        ),
                    )
                    if response.text:
                        return response.text[:2000]
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "403" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        km.mark_rate_limited(key, cooldown=300)
                        continue
                    break

        return "Google Search error: All models and keys exhausted"

    except ImportError:
        return "Google GenAI SDK not available."
    except Exception as e:
        return f"Google Search error: {e}"


# ═══════════════════════════════════════════════════════════════
#  GOOGLE AI STUDIO — MAPS GROUNDING (Priority 1 for location)
# ═══════════════════════════════════════════════════════════════

def google_maps_grounding(query: str, lat: float = None, lng: float = None) -> str:
    """Search nearby places using Gemini's Google Maps grounding — rotate ALL keys per model."""
    try:
        from google import genai
        from google.genai import types
        from key_manager import APIKeyManager
        from config import SEARCH_MODELS

        if lat is None or lng is None:
            try:
                from settings_manager import get_user_location
                lat, lng = get_user_location()
            except ImportError:
                lat, lng = 19.8762, 75.3704

        km = APIKeyManager()

        for model in SEARCH_MODELS:
            for _ in range(len(km.state["api_keys"])):
                key = km.get_key()
                if not key:
                    break
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model=model,
                        contents=query,
                        config=types.GenerateContentConfig(
                            tools=[types.Tool(google_maps=types.GoogleMaps())],
                            tool_config=types.ToolConfig(
                                retrieval_config=types.RetrievalConfig(
                                    lat_lng=types.LatLng(
                                        latitude=lat,
                                        longitude=lng,
                                    ),
                                ),
                            ),
                        ),
                    )
                    if response.text:
                        return response.text[:2000]
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "403" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        km.mark_rate_limited(key, cooldown=300)
                        continue
                    break

        return "Google Maps error: All models and keys exhausted"

    except ImportError:
        return "Google GenAI SDK not available."
    except Exception as e:
        return f"Google Maps error: {e}"


def google_dual_grounding(query: str, lat: float = None, lng: float = None) -> str:
    """Dual grounding: Google Search + Google Maps — rotate ALL keys per model."""
    try:
        from google import genai
        from google.genai import types
        from key_manager import APIKeyManager
        from config import SEARCH_MODELS

        if lat is None or lng is None:
            try:
                from settings_manager import get_user_location
                lat, lng = get_user_location()
            except ImportError:
                lat, lng = 19.8762, 75.3704

        km = APIKeyManager()

        for model in SEARCH_MODELS:
            for _ in range(len(km.state["api_keys"])):
                key = km.get_key()
                if not key:
                    break
                try:
                    client = genai.Client(api_key=key)
                    response = client.models.generate_content(
                        model=model,
                        contents=query,
                        config=types.GenerateContentConfig(
                            tools=[
                                types.Tool(google_search=types.GoogleSearch()),
                                types.Tool(google_maps=types.GoogleMaps()),
                            ],
                            tool_config=types.ToolConfig(
                                retrieval_config=types.RetrievalConfig(
                                    lat_lng=types.LatLng(
                                        latitude=lat,
                                        longitude=lng,
                                    ),
                                ),
                            ),
                        ),
                    )
                    if response.text:
                        return response.text[:2000]
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "403" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        km.mark_rate_limited(key, cooldown=300)
                        continue
                    break

        return "Google Dual Grounding error: All models and keys exhausted"

    except ImportError:
        return "Google GenAI SDK not available."
    except Exception as e:
        return f"Google Dual Grounding error: {e}"


# ═══════════════════════════════════════════════════════════════
#  TAVILY SEARCH (Priority 2)
# ═══════════════════════════════════════════════════════════════

_TAVILY_KEYS = []
_tavily_cycle = None


def _load_tavily_keys():
    """Load Tavily keys from .env."""
    global _TAVILY_KEYS, _tavily_cycle
    if _TAVILY_KEYS:
        return

    raw = os.getenv("TAVILY_API_KEY", "")
    if raw:
        _TAVILY_KEYS = [k.strip() for k in raw.split(",") if k.strip()]

    if _TAVILY_KEYS:
        _tavily_cycle = cycle(_TAVILY_KEYS)


def tavily_search(query: str, max_results: int = 5) -> str:
    """Search using Tavily API with key rotation."""
    _load_tavily_keys()

    if not _TAVILY_KEYS:
        return "Tavily error: No API keys configured. Set TAVILY_API_KEY in .env"

    last_error = None
    for _ in range(len(_TAVILY_KEYS)):
        api_key = next(_tavily_cycle)
        try:
            payload = json.dumps({
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_answer": True,
                "include_raw_content": False,
            }).encode()

            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            answer = data.get("answer", "")
            results = data.get("results", [])
            parts = []
            if answer:
                parts.append(f"**Answer:** {answer}")
            for r in results[:max_results]:
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("content", "")[:200]
                parts.append(f"- **{title}**\n  {url}\n  {snippet}")
            return "\n".join(parts) if parts else "No Tavily results."

        except Exception as e:
            last_error = e
            continue

    return f"Tavily error: {last_error}"


# ═══════════════════════════════════════════════════════════════
#  DUCKDUCKGO SEARCH (Priority 3 — free fallback)
# ═══════════════════════════════════════════════════════════════

def duckduckgo_search(query: str, max_results: int = 5) -> str:
    """Search using DuckDuckGo Instant Answers API (no key needed)."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "IRA/2.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        parts = []

        answer = data.get("Answer", "")
        if answer:
            parts.append(f"**Quick Answer:** {answer}")

        abstract = data.get("AbstractText", "")
        if abstract:
            source = data.get("AbstractSource", "")
            url_src = data.get("AbstractURL", "")
            parts.append(f"**{source}:** {abstract}")
            if url_src:
                parts.append(f"  {url_src}")

        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict):
                text = topic.get("Text", "")
                first_url = topic.get("FirstURL", "")
                if text:
                    parts.append(f"- {text[:200]}")
                    if first_url:
                        parts.append(f"  {first_url}")

        return "\n".join(parts) if parts else "No DuckDuckGo results."

    except Exception as e:
        return f"DuckDuckGo error: {e}"


# ═══════════════════════════════════════════════════════════════
#  WIKIPEDIA (Always-on parallel)
# ═══════════════════════════════════════════════════════════════

def wikipedia_search(query: str) -> str:
    """Search Wikipedia for a topic summary."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "IRA/2.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        title = data.get("title", "")
        extract = data.get("extract", "No summary available.")
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

        parts = [f"**Wikipedia — {title}:**", extract[:1500]]
        if page_url:
            parts.append(f"  {page_url}")
        return "\n".join(parts)

    except urllib.error.HTTPError:
        return f"Wikipedia: No article found for '{query}'."
    except Exception as e:
        return f"Wikipedia error: {e}"


# ═══════════════════════════════════════════════════════════════
#  REDDIT (Always-on parallel)
# ═══════════════════════════════════════════════════════════════

def reddit_search(query: str, max_results: int = 5) -> str:
    """Search Reddit via Jina AI reader for real discussions."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://s.jina.ai/reddit+{encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "IRA/2.0",
            "Accept": "text/plain",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")

        if not text or len(text.strip()) < 20:
            return "No Reddit results found."

        return text[:2000]

    except Exception as e:
        return f"Reddit search error: {e}"


# ═══════════════════════════════════════════════════════════════
#  JINA AI (Last resort fallback)
# ═══════════════════════════════════════════════════════════════

def jina_search(query: str) -> str:
    """Search using Jina AI reader for any URL or query."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://s.jina.ai/{encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "IRA/2.0",
            "Accept": "text/plain",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")

        if not text or len(text.strip()) < 20:
            return "No Jina results found."

        return text[:2000]

    except Exception as e:
        return f"Jina search error: {e}"


# ═══════════════════════════════════════════════════════════════
#  NEARBY SEARCH — Google Maps grounding for location queries
# ═══════════════════════════════════════════════════════════════

def nearby_search(query: str, lat: float = None, lng: float = None) -> str:
    """Search nearby places using Google Maps grounding (AI Studio free).
    
    Priority: Google Maps → Tavily → DuckDuckGo
    Always parallel: Wikipedia + Reddit (if query is a topic)
    """
    results = []
    engines_used = []

    # ── [1] Google Maps grounding (highest priority for location queries) ──
    maps_result = google_maps_grounding(
        f"Find nearby places: {query}. List them with name, address, and distance.",
        lat=lat, lng=lng,
    )
    if not maps_result.startswith("Google Maps error"):
        results.append(f"**Google Maps:**\n{maps_result}")
        engines_used.append("Google Maps")

    # ── [2] Tavily fallback ──
    if not results:
        tavily_result = tavily_search(f"nearby {query}")
        if not tavily_result.startswith("Tavily error") and "No Tavily" not in tavily_result:
            results.append(f"**Tavily:**\n{tavily_result}")
            engines_used.append("Tavily")

    # ── [3] DuckDuckGo fallback ──
    if not results:
        ddg_result = duckduckgo_search(f"nearby {query}")
        if not ddg_result.startswith("DuckDuckGo error") and "No DuckDuckGo" not in ddg_result:
            results.append(f"**DuckDuckGo:**\n{ddg_result}")
            engines_used.append("DuckDuckGo")

    if not results:
        return f"No nearby results found for: {query}"

    header = f"Nearby search ({', '.join(engines_used)}):\n{'─' * 40}\n\n"
    return header + "\n\n".join(results)


# ═══════════════════════════════════════════════════════════════
#  PLACE DETAILS — Dual grounding for specific places
# ═══════════════════════════════════════════════════════════════

def place_details(query: str, lat: float = None, lng: float = None) -> str:
    """Get detailed info about a specific place using dual grounding.
    
    Uses both Google Search + Google Maps in a single API call.
    Gets: address, reviews, contact, hours, directions.
    """
    try:
        from settings_manager import get_user_location, get_user_city
        if lat is None or lng is None:
            lat, lng = get_user_location()
        user_city = get_user_city()
    except ImportError:
        if lat is None:
            lat, lng = 19.8762, 75.3704
        user_city = "Chhatrapati Sambhajinagar"

    # Dual grounding: Search + Maps together
    prompt = (
        f"Get full details about: {query}\n"
        f"User location: {user_city} (lat: {lat}, lng: {lng})\n\n"
        f"Provide:\n"
        f"1. Full address\n"
        f"2. Contact number (if available)\n"
        f"3. Operating hours\n"
        f"4. Rating and reviews summary\n"
        f"5. What they are known for\n"
        f"6. How to reach there from {user_city} — approximate distance and travel time by walk, cycle, and car\n"
        f"7. Google Maps link\n\n"
        f"Be concise and structured."
    )

    result = google_dual_grounding(prompt, lat=lat, lng=lng)

    if result.startswith("Google Dual Grounding error"):
        # Fallback to Maps-only
        result = google_maps_grounding(
            f"Get details about: {query}. Include address, contact, hours, and distance from {user_city}.",
            lat=lat, lng=lng,
        )

    if result.startswith("Google Maps error"):
        # Fallback to Tavily
        result = tavily_search(f"{query} details address contact hours")

    return result


# ═══════════════════════════════════════════════════════════════
#  UNIFIED SEARCH — THE ULTIMATE SEARCH KING
# ═══════════════════════════════════════════════════════════════

def ultimate_search(query: str, engines: str = "auto") -> str:
    """
    Multi-engine search with Google-first priority chain.
    
    engines: "auto" | "all" | "google" | "tavily" | "ddg" | "wiki" | "reddit" | "jina"
    
    Auto mode priority:
    [1] Google AI Studio grounding (search + maps) — ALWAYS FIRST
    [2] Tavily (if Google fails)
    [3] DuckDuckGo (if Tavily fails)
    [4] Jina AI (last resort)
    
    Wikipedia & Reddit are queried only if explicitly requested, as a fallback, 
    or if the query specifically targets definitions, history, discussions, or reviews.
    """
    results = []
    engines_used = []
    primary_found = False

    # ── Primary chain: Google → Tavily → DDG → Jina ──
    # [1] Google AI Studio grounding (ALWAYS FIRST)
    if engines in ("auto", "all", "google"):
        google = google_search_grounding(query)
        if not google.startswith("Google Search error"):
            results.append(f"🌐 **Google:**\n{google}")
            engines_used.append("Google")
            primary_found = True

    # [2] Tavily (if Google fails)
    if not primary_found and engines in ("auto", "all", "tavily"):
        tavily = tavily_search(query)
        if not tavily.startswith("Tavily error") and "No Tavily results" not in tavily:
            results.append(f"🔍 **Tavily:**\n{tavily}")
            engines_used.append("Tavily")
            primary_found = True

    # [3] DuckDuckGo (if Tavily fails)
    if not primary_found and engines in ("auto", "all", "ddg"):
        ddg = duckduckgo_search(query)
        if not ddg.startswith("DuckDuckGo error") and "No DuckDuckGo results" not in ddg:
            results.append(f"🦆 **DuckDuckGo:**\n{ddg}")
            engines_used.append("DuckDuckGo")
            primary_found = True

    # [4] Jina AI (last resort)
    if not primary_found and engines in ("auto", "all", "jina"):
        jina = jina_search(query)
        if not jina.startswith("Jina search error") and "No Jina results" not in jina:
            results.append(f"🤖 **Jina AI:**\n{jina}")
            engines_used.append("Jina")

    # ── Conditional Wikipedia & Reddit searches ──
    query_lower = query.lower()
    
    # Check if Wikipedia context is relevant
    needs_wiki = (engines == "wiki") or (engines == "all") or (engines == "auto" and not primary_found) or (
        engines == "auto" and any(k in query_lower for k in ("wikipedia", "wiki", "define", "definition", "history", "who is", "what is"))
    )
    
    # Check if Reddit discussion context is relevant
    needs_reddit = (engines == "reddit") or (engines == "all") or (engines == "auto" and not primary_found) or (
        engines == "auto" and any(k in query_lower for k in ("reddit", "forum", "discussion", "review", "opinion", "people say", "community"))
    )

    if needs_wiki:
        wiki = wikipedia_search(query)
        if not wiki.startswith("Wikipedia: No article"):
            results.append(f"📚 **Wikipedia:**\n{wiki}")
            engines_used.append("Wikipedia")

    if needs_reddit:
        reddit = reddit_search(query)
        if not reddit.startswith("No Reddit") and not reddit.startswith("Reddit search error"):
            results.append(f"💬 **Reddit:**\n{reddit}")
            engines_used.append("Reddit")

    if not results:
        return f"No results found across any search engine for: {query}"

    header = f"Search ({', '.join(engines_used)}):\n{'─' * 40}\n\n"
    return header + "\n\n".join(results)


# ═══════════════════════════════════════════════════════════════
#  OSRM ROUTING (Free, no key)
# ═══════════════════════════════════════════════════════════════

def osrm_route(lat1: float, lng1: float, lat2: float, lng2: float, profile: str = "car") -> dict:
    """Get route between two points using OSRM (free, no key).
    
    profile: "car" | "bike" | "foot"
    Returns: {distance, duration, distance_text, duration_text, coords}
    """
    profiles = {
        "car": "driving",
        "bike": "cycling",
        "foot": "walking",
    }
    osrm_profile = profiles.get(profile, "driving")

    try:
        url = (
            f"https://router.project-osrm.org/route/v1/{osrm_profile}/"
            f"{lng1},{lat1};{lng2},{lat2}"
            f"?overview=full&geometries=geojson&steps=true"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "IRA/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        if data.get("code") != "Ok" or not data.get("routes"):
            return {"error": "No route found"}

        route = data["routes"][0]
        distance_m = route.get("distance", 0)
        duration_s = route.get("duration", 0)

        # Format distance
        if distance_m >= 1000:
            dist_text = f"{distance_m / 1000:.1f}km"
        else:
            dist_text = f"{int(distance_m)}m"

        # Format duration
        mins = int(duration_s / 60)
        if mins >= 60:
            hours = mins // 60
            mins = mins % 60
            dur_text = f"{hours}h {mins}min"
        else:
            dur_text = f"{mins} min"

        # Extract route coordinates
        coords = []
        geom = route.get("geometry", {})
        for coord in geom.get("coordinates", []):
            coords.append([coord[1], coord[0]])  # [lat, lng]

        return {
            "distance": distance_m,
            "duration": duration_s,
            "distance_text": dist_text,
            "duration_text": dur_text,
            "coords": coords,
        }

    except Exception as e:
        return {"error": str(e)}


def get_route_summary(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    """Get walking, cycling, and driving route summary between two points."""
    walk = osrm_route(lat1, lng1, lat2, lng2, "foot")
    cycle = osrm_route(lat1, lng1, lat2, lng2, "bike")
    drive = osrm_route(lat1, lng1, lat2, lng2, "car")

    parts = []
    if not walk.get("error"):
        parts.append(f"🚶 Walk: {walk['duration_text']} ({walk['distance_text']})")
    if not cycle.get("error"):
        parts.append(f"🚲 Cycle: {cycle['duration_text']} ({cycle['distance_text']})")
    if not drive.get("error"):
        parts.append(f"🚗 Drive: {drive['duration_text']} ({drive['distance_text']})")

    return "\n".join(parts) if parts else "No route found."


def get_route_for_map(lat1: float, lng1: float, lat2: float, lng2: float) -> dict:
    """Get all three route types for map display."""
    walk = osrm_route(lat1, lng1, lat2, lng2, "foot")
    cycle = osrm_route(lat1, lng1, lat2, lng2, "bike")
    drive = osrm_route(lat1, lng1, lat2, lng2, "car")

    return {
        "walk": walk if not walk.get("error") else None,
        "cycle": cycle if not cycle.get("error") else None,
        "drive": drive if not drive.get("error") else None,
    }


# ═══════════════════════════════════════════════════════════════
#  PLACE COORDINATE EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_place_coords(text: str) -> list[dict]:
    """Extract place names and coordinates from Google Maps grounding response.
    
    Returns: [{name, lat, lng, address, distance}, ...]
    """
    import re
    places = []

    # Try to find coordinate patterns like (18.4012, 76.5689)
    coord_pattern = r'\((\d+\.\d+),\s*(\d+\.\d+)\)'
    coords_found = re.findall(coord_pattern, text)

    # Try to find distance patterns like "468 meters" or "1.2 kilometers"
    dist_pattern = r'(\d+(?:\.\d+)?)\s*(meters?|kilometers?|km|m)'
    distances = re.findall(dist_pattern, text, re.IGNORECASE)

    # Try to find place names - look for bold text or numbered items
    name_patterns = [
        r'\*\*(.+?)\*\*',  # **Bold text**
        r'(\d+)\.\s*(.+?)(?:\s*[-–—]|\s*$)',  # 1. Place Name -
        r'[•●]\s*(.+?)(?:\s*[-–—])',  # • Place Name -
    ]

    for pattern in name_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            name = match if isinstance(match, str) else match[1] if len(match) > 1 else match[0]
            if name and len(name) > 3 and len(name) < 100:
                places.append({"name": name.strip("*")})

    # Associate coords with places if we have matching counts
    for i, place in enumerate(places):
        if i < len(coords_found):
            place["lat"] = float(coords_found[i][0])
            place["lng"] = float(coords_found[i][1])
        if i < len(distances):
            place["distance"] = f"{distances[i][0]} {distances[i][1]}"

    return places
