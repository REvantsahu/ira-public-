"API Key Manager — Multi-key rotation with per-tool state files."

import time
from config import COOLDOWN_SECONDS
from state_manager import (
    init, get_sorted_keys, mark_key_dead, mark_key_rate_limited,
    mark_key_success, cleanup_expired, save_state
)


class APIKeyManager:
    def __init__(self, state_file=None):
        self.state_file = state_file
        self.state = init(state_file)
        self.keys = get_sorted_keys(self.state)
        self.current_index = 0

    def get_key(self):
        cleanup_expired(self.state, self.state_file)
        self.keys = get_sorted_keys(self.state)

        alive = [k for k in self.keys if not k["dead"]]
        if not alive:
            return None

        now = time.time()
        for _ in range(len(self.keys)):
            key = self.keys[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.keys)

            if key["dead"]:
                continue
            rl = key.get("rate_limited_until")
            if rl and rl > now:
                continue
            mark_key_success(self.state, key["key"])
            return key["key"]

        return None

    def mark_rate_limited(self, key, cooldown=None):
        mark_key_rate_limited(self.state, key, cooldown)

    def mark_dead(self, key, reason="banned"):
        mark_key_dead(self.state, key, reason)

    def report(self):
        cleanup_expired(self.state, self.state_file)
        now = time.time()
        active = dead_count = rl_count = 0
        for k in self.state["api_keys"]:
            if k["dead"]:
                dead_count += 1
            else:
                rl_val = k.get("rate_limited_until")
                if rl_val is not None and rl_val > now:
                    rl_count += 1
                else:
                    active += 1
        parts = [f"{active}/{len(self.state['api_keys'])} available"]
        if rl_count:
            parts.append(f"{rl_count} cooling")
        if dead_count:
            parts.append(f"{dead_count} dead")
        return " | ".join(parts)
