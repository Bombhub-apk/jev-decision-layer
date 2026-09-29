import os
import sys
import json
import winreg
from pathlib import Path
from datetime import datetime

KEYS_FILE = Path(os.path.expanduser("~/.gemini/antigravity/jev_keys.json"))

def mask_key(key: str) -> str:
    if not key or len(key) < 12:
        return "****"
    return f"{key[:8]}...{key[-6:]}"

def get_env_or_registry_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key and os.name == "nt":
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                val, _ = winreg.QueryValueEx(handle, "TYPESAFE_API_KEY")
                key = val.strip() if isinstance(val, str) else ""
        except FileNotFoundError:
            pass
    return key

def load_config() -> dict:
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not KEYS_FILE.exists() or KEYS_FILE.stat().st_size == 0:
        default_key = get_env_or_registry_key()
        keys_list = []
        if default_key:
            keys_list.append({
                "name": "primary",
                "key": default_key,
                "status": "active",
                "calls": 7,
                "tokens": 3905,
                "added_at": datetime.now().isoformat(timespec="seconds")
            })
        config = {
            "strategy": "round_robin",  # "round_robin" or "single"
            "active_key_name": "primary" if keys_list else None,
            "current_index": 0,
            "keys": keys_list
        }
        save_config(config)
        return config
    
    try:
        data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        # Ensure schema structure
        if "keys" not in data:
            data["keys"] = []
        if "strategy" not in data:
            data["strategy"] = "round_robin"
        if "current_index" not in data:
            data["current_index"] = 0
        return data
    except Exception:
        return {"strategy": "round_robin", "active_key_name": None, "current_index": 0, "keys": []}

def save_config(config: dict):
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEYS_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

def add_key(name: str, key_val: str, status: str = "active") -> dict:
    config = load_config()
    key_val = key_val.strip()
    name = name.strip().lower()
    
    # Check if key already exists by name
    existing = next((k for k in config["keys"] if k["name"] == name), None)
    if existing:
        existing["key"] = key_val
        existing["status"] = status
    else:
        config["keys"].append({
            "name": name,
            "key": key_val,
            "status": status,
            "calls": 0,
            "tokens": 0,
            "added_at": datetime.now().isoformat(timespec="seconds")
        })
    if not config.get("active_key_name"):
        config["active_key_name"] = name
    save_config(config)
    return {"status": "ok", "name": name, "masked": mask_key(key_val)}

def remove_key(name: str) -> bool:
    config = load_config()
    name = name.strip().lower()
    initial_len = len(config["keys"])
    config["keys"] = [k for k in config["keys"] if k["name"] != name]
    if len(config["keys"]) < initial_len:
        if config.get("active_key_name") == name:
            config["active_key_name"] = config["keys"][0]["name"] if config["keys"] else None
        save_config(config)
        return True
    return False

def list_keys() -> list:
    config = load_config()
    result = []
    active_keys = [k for k in config.get("keys", []) if k.get("status") == "active"]
    curr_idx = config.get("current_index", 0)
    next_key_name = active_keys[curr_idx % len(active_keys)]["name"] if active_keys else None
    for k in config.get("keys", []):
        result.append({
            "name": k["name"],
            "masked": mask_key(k["key"]),
            "status": k.get("status", "active"),
            "calls": k.get("calls", 0),
            "tokens": k.get("tokens", 0),
            "is_next": (k["name"] == next_key_name and config.get("strategy") == "round_robin" and k.get("status") == "active"),
            "is_active_target": (k["name"] == config.get("active_key_name"))
        })
    return result

def set_strategy(strategy: str):
    config = load_config()
    strategy = strategy.strip().lower()
    if strategy in ("round_robin", "round-robin", "rr"):
        config["strategy"] = "round_robin"
    elif strategy in ("single", "fixed"):
        config["strategy"] = "single"
    save_config(config)
    return config["strategy"]

def set_active_key(name: str) -> bool:
    config = load_config()
    name = name.strip().lower()
    match = next((k for k in config["keys"] if k["name"] == name), None)
    if match:
        config["active_key_name"] = name
        save_config(config)
        return True
    return False

def edit_key(name: str, new_name: str = None, key_val: str = None, status: str = None) -> bool:
    config = load_config()
    name = name.strip().lower()
    key_entry = next((k for k in config["keys"] if k["name"] == name), None)
    if not key_entry:
        return False
    if new_name:
        new_name_clean = new_name.strip().lower()
        if new_name_clean != name and any(k["name"] == new_name_clean for k in config["keys"]):
            raise ValueError(f"Key with name '{new_name_clean}' already exists.")
        key_entry["name"] = new_name_clean
        if config.get("active_key_name") == name:
            config["active_key_name"] = new_name_clean
    if key_val and key_val.strip():
        key_entry["key"] = key_val.strip()
    if status in ("active", "inactive", "rate_limited"):
        key_entry["status"] = status
    save_config(config)
    return True

def toggle_key_status(name: str) -> str:
    config = load_config()
    name = name.strip().lower()
    key_entry = next((k for k in config["keys"] if k["name"] == name), None)
    if not key_entry:
        raise ValueError(f"Key '{name}' not found.")
    current_status = key_entry.get("status", "active")
    new_status = "inactive" if current_status == "active" else "active"
    key_entry["status"] = new_status
    save_config(config)
    return new_status

def get_next_key() -> tuple[str, str]:
    """
    Selects the next API key based on strategy (Round-Robin or Single).
    Returns (api_key_value, key_name).
    """
    config = load_config()
    active_keys = [k for k in config["keys"] if k.get("status") == "active"]
    
    if not active_keys:
        # Fallback to env or registry
        env_key = get_env_or_registry_key()
        if env_key:
            return env_key, "env_fallback"
        raise ValueError("No active TypeSafe API keys found in pool or environment.")
        
    strategy = config.get("strategy", "round_robin")
    
    if strategy == "single":
        target_name = config.get("active_key_name")
        selected = next((k for k in active_keys if k["name"] == target_name), active_keys[0])
        return selected["key"], selected["name"]
        
    # Round-Robin strategy
    curr_idx = config.get("current_index", 0)
    if curr_idx >= len(active_keys):
        curr_idx = 0
        
    selected = active_keys[curr_idx]
    
    # Increment pointer to next active key for next turn
    next_idx = (curr_idx + 1) % len(active_keys)
    config["current_index"] = next_idx
    save_config(config)
    
    return selected["key"], selected["name"]

def record_key_usage(name: str, tokens: int):
    config = load_config()
    for k in config["keys"]:
        if k["name"] == name:
            k["calls"] = k.get("calls", 0) + 1
            k["tokens"] = k.get("tokens", 0) + tokens
            break
    save_config(config)

def mark_key_status(name: str, status: str):
    config = load_config()
    for k in config["keys"]:
        if k["name"] == name:
            k["status"] = status
            break
    save_config(config)
