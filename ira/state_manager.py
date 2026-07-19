"Persistent state for API keys — separate state per tool (image/video/music/text)."

import json, os, time
from config import GEMINI_KEYS, MODELS_FALLBACK, COOLDOWN_SECONDS

_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE_FILE = os.path.join(_DIR, "state.json")


def _entry(key_or_name, idx, is_key=True):
    e = {"priority": idx, "dead": False, "last_error": None}
    if is_key:
        e["key"] = key_or_name
    else:
        e["name"] = key_or_name
    return e


def _default_state():
    return {
        "api_keys": [_entry(k, i) for i, k in enumerate(GEMINI_KEYS)],
        "models": [_entry(m, i, is_key=False) for i, m in enumerate(MODELS_FALLBACK)],
        "version": 1,
    }


def load_state(state_file=None):
    sf = state_file or DEFAULT_STATE_FILE
    if os.path.exists(sf):
        try:
            with open(sf, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("api_keys", [])
            data.setdefault("models", [])
            return data
        except (json.JSONDecodeError, KeyError):
            pass
    return _default_state()


def save_state(state, state_file=None):
    sf = state_file or state.get("_state_file") or DEFAULT_STATE_FILE
    state_copy = dict(state)
    state_copy.pop("_state_file", None)
    state_copy["last_updated"] = time.time()
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(state_copy, f, indent=2, ensure_ascii=False)


def _merge_keys(state):
    persisted = {k["key"]: k for k in state.get("api_keys", [])}
    merged = []
    for i, key in enumerate(GEMINI_KEYS):
        if key in persisted:
            entry = persisted[key]
            entry.pop("cooldown_until", None)
            merged.append(entry)
        else:
            merged.append(_entry(key, i))
    state["api_keys"] = merged
    return state


def _merge_models(state):
    persisted = {m["name"]: m for m in state.get("models", [])}
    merged = []
    for i, model in enumerate(MODELS_FALLBACK):
        if model in persisted:
            entry = persisted[model]
            merged.append(entry)
        else:
            merged.append(_entry(model, i, is_key=False))
    state["models"] = merged
    return state


def init(state_file=None):
    sf = state_file or DEFAULT_STATE_FILE
    state = load_state(sf)
    state["_state_file"] = sf
    state = _merge_keys(state)
    state = _merge_models(state)
    save_state(state, sf)
    return state


def get_sorted_keys(state):
    alive = [k for k in state["api_keys"] if not k["dead"]]
    dead = [k for k in state["api_keys"] if k["dead"]]
    alive.sort(key=lambda k: (k.get("priority", 999), k.get("last_error") or ""))
    return alive + dead


def get_sorted_models(state):
    alive = [m for m in state["models"] if not m["dead"]]
    dead = [m for m in state["models"] if m["dead"]]
    alive.sort(key=lambda m: (m.get("priority", 999), m.get("last_error") or ""))
    return alive + dead


def mark_key_dead(state, key_str, reason=""):
    for k in state["api_keys"]:
        if k["key"] == key_str:
            k["dead"] = True
            k["last_error"] = f"dead:{reason}"
            k.pop("rate_limited_until", None)
            break
    save_state(state)


def mark_key_rate_limited(state, key_str, cooldown=None):
    cd = cooldown or COOLDOWN_SECONDS
    for k in state["api_keys"]:
        if k["key"] == key_str:
            k["rate_limited_until"] = time.time() + cd
            k["priority"] = max(e["priority"] for e in state["api_keys"]) + 1
            k["last_error"] = f"rate_limited:{time.time()}"
            break
    save_state(state)


def mark_key_success(state, key_str):
    changed = False
    for k in state["api_keys"]:
        if k["key"] == key_str and k.get("last_error"):
            k["last_error"] = None
            k.pop("rate_limited_until", None)
            changed = True
            break
    if changed:
        save_state(state)


def mark_model_rate_limited(state, model_name):
    for m in state["models"]:
        if m["name"] == model_name:
            m["rate_limited_until"] = time.time() + COOLDOWN_SECONDS
            m["priority"] = max(e["priority"] for e in state["models"]) + 1
            m["last_error"] = f"rate_limited:{time.time()}"
            break
    save_state(state)


def mark_model_dead(state, model_name, reason=""):
    for m in state["models"]:
        if m["name"] == model_name:
            m["dead"] = True
            m["last_error"] = f"dead:{reason}"
            m.pop("rate_limited_until", None)
            break
    save_state(state)


def mark_model_success(state, model_name):
    changed = False
    for m in state["models"]:
        if m["name"] == model_name and m.get("last_error"):
            m["last_error"] = None
            m.pop("rate_limited_until", None)
            changed = True
            break
    if changed:
        save_state(state)


def cleanup_expired(state, state_file=None):
    now = time.time()
    changed = False
    for entry in state["api_keys"] + state["models"]:
        rl = entry.get("rate_limited_until")
        if rl is not None and rl <= now:
            entry.pop("rate_limited_until", None)
            entry["last_error"] = None
            changed = True
    if changed:
        save_state(state, state_file)
