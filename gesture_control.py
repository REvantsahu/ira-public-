"""IRA Gesture Controller — maps hand state to REAL system actions.

Sits between the MediaPipe gesture_engine (which only detects) and the OS
(which actually moves the mouse / clicks / scrolls). Pure math + a small
state machine + tool dispatch. No camera, no MediaPipe imports here.

Flow:
    gesture_engine._on_state(hand_state)  ->  controller.process(hand_state)
                                                    |
                          ┌─────────────────────────┼───────────────────────┐
                          ▼                         ▼                       ▼
                   One Euro filter          Engage FSM             action dispatch
                   (smooth cursor)          (fist-hold >250ms)     (move_mouse/click/scroll)

The controller also publishes a rich `control_state` dict that hud_overlay emits
to QML so the HUD can draw the particle trail, engage ring and burst FX.
"""

from __future__ import annotations

import math
import time
import threading


# ── One Euro Filter ────────────────────────────────────────
# Classic adaptive low-pass filter for noisy pointer input.
# At low speed it smooths aggressively (kills jitter); at high speed it
# follows nearly 1:1 (no lag). Reference: Casiez et al. 2012.

class _OneEuroFilter:
    def __init__(self, freq: float = 60.0, min_cutoff: float = 1.2,
                 beta: float = 0.02, d_cutoff: float = 1.0):
        self.freq = freq
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _alpha(cutoff: float, dt: float, d_cutoff: float = 1.0) -> float:
        if dt <= 0:
            return 1.0
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + (tau / dt))

    def filter(self, x: float, dt: float | None = None) -> float:
        now = time.time()
        if self._t_prev is None:
            self._t_prev = now
            self._x_prev = x
            return x
        if dt is None:
            dt = max(now - self._t_prev, 1e-4)
        dt = min(dt, 1.0)  # clamp huge gaps (e.g. after a stall)
        self.freq = 1.0 / dt if dt > 0 else self.freq

        # Estimate derivative
        dx = (x - self._x_prev) * self.freq
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev

        # Estimate value, cutoff rises with speed
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = now
        return x_hat


# ── State machine ──────────────────────────────────────────

class _State:
    IDLE = "idle"          # tracking only, no clicks/control
    ARMED = "armed"        # fist detected, holding to confirm engage
    ENGAGED = "engaged"    # active control: cursor moves + pinch clicks
    COOLDOWN = "cooldown"  # just released, brief lockout


# ── Controller ─────────────────────────────────────────────

class GestureController:
    """Maps continuous hand state to real OS actions with an engage gate.

    Engage model: hold a fist > ENGAGE_HOLD seconds -> ENGAGED.
    While engaged the index finger drives the real cursor (One Euro smoothed),
    a pinch performs a left click, an open palm drives scroll. Releasing the
    fist disengages after a short grace period.
    """

    def __init__(self):
        # Tunables
        self.engage_hold = 0.25       # seconds of fist to engage
        self.disengage_grace = 0.35   # seconds of no-fist before disengage
        self.deadzone = 0.012         # normalized — ignore drift below this
        self.scroll_threshold = 0.045  # normalized y-delta per scroll tick
        self.click_cooldown = 0.45    # min seconds between pinch clicks
        self.trail_max = 24           # trail points kept for FX
        self.trail_ttl = 0.45         # seconds before a trail point fades

        # Smoothing — two independent filters, mirror handled by caller
        self._fx = _OneEuroFilter(min_cutoff=1.4, beta=0.018)
        self._fy = _OneEuroFilter(min_cutoff=1.4, beta=0.018)

        # FSM
        self.state = _State.IDLE
        self._fist_since = 0.0        # when current fist hold started
        self._no_fist_since = 0.0     # when fist was last released
        self._enabled = True          # global kill switch (settings/voice)
        self.system_control = True    # master toggle for real OS actions

        # Click / scroll edge detection
        self._was_pinch = False
        self._last_click = 0.0
        self._was_dragging = False     # fist-held while engaged -> drag
        self._scroll_accum = 0.0
        self._last_index_y = None

        # Cursor
        self._screen_w = 1920
        self._screen_h = 1080
        self._cursor_x = 0.5
        self._cursor_y = 0.5
        self._landmarks = []           # normalized landmark list for FX overlay

        # Trail (list of {x, y, t})
        self._trail: list[dict] = []

        # Burst events (QML consumes + clears)
        self._burst_queue: list[dict] = []

        # Last published action label for HUD readout
        self.last_action = "none"

        self._lock = threading.Lock()

    # ── lifecycle ──

    def configure_screen(self, width: int, height: int):
        self._screen_w = max(1, int(width))
        self._screen_h = max(1, int(height))

    def enable(self):
        self._enabled = True

    def disable(self):
        """Pause control but keep reporting state. Used by voice mode / settings."""
        self._enabled = False
        self._reset_edges()

    def is_engaged(self) -> bool:
        return self.state == _State.ENGAGED

    # ── main entry: called every frame with primary hand state ──

    def process(self, hand_state: dict | None) -> dict:
        """Consume one hand_state frame; return the control_state for QML."""
        with self._lock:
            now = time.time()

            if not hand_state or not self._enabled:
                self._advance_fsm(now, fist=False, pinch=False, open_palm=False)
                self._expire_trail(now)
                return self._publish(now, active=False)

            index = hand_state.get("index", {}) or {}
            nx = float(index.get("x", 0.5))
            ny = float(index.get("y", 0.5))
            fist = bool(hand_state.get("fist"))
            pinch = bool(hand_state.get("pinch"))
            open_palm = bool(hand_state.get("open_palm"))
            total_up = int(hand_state.get("total_up", 0))

            # Mirror is applied by the caller (hud_overlay) to match the
            # camera preview; we receive already-mirrored normalized coords.
            self._advance_fsm(now, fist=fist, pinch=pinch, open_palm=open_palm)

            active = self.state == _State.ENGAGED and self.system_control

            # ALWAYS smooth + track the cursor so the HUD trail/reticle follows
            # the finger even before engage. Only the OS actions below are gated.
            sx_n = self._fx.filter(nx)
            sy_n = self._fy.filter(ny)
            if (abs(sx_n - self._cursor_x) > self.deadzone or
                    abs(sy_n - self._cursor_y) > self.deadzone):
                self._cursor_x = sx_n
                self._cursor_y = sy_n

            if active:
                # Move the real cursor to follow the finger
                px = self._to_pixel(sx_n, self._screen_w)
                py = self._to_pixel(sy_n, self._screen_h)
                if not self._was_dragging:
                    self._do("move_mouse", {"x": px, "y": py})

                # Pinch -> click (rising edge + cooldown)
                if pinch and not self._was_pinch:
                    if now - self._last_click >= self.click_cooldown:
                        self._last_click = now
                        self._do("click", {})
                        self._burst_queue.append({"x": self._cursor_x,
                                                  "y": self._cursor_y,
                                                  "kind": "click"})
                        self.last_action = "click"

                # Fist-held while engaged -> drag (hold mouse button)
                if fist:
                    if not self._was_dragging:
                        # start drag at current cursor
                        self._do_drag(True)
                        self._was_dragging = True
                        self.last_action = "drag"
                else:
                    if self._was_dragging:
                        self._do_drag(False)
                        self._was_dragging = False

                # Open palm -> scroll by accumulated vertical motion
                if open_palm and total_up >= 4:
                    if self._last_index_y is not None:
                        delta = ny - self._last_index_y
                        self._scroll_accum += delta
                        if abs(self._scroll_accum) >= self.scroll_threshold:
                            direction = "up" if self._scroll_accum < 0 else "down"
                            self._do("scroll", {"direction": direction, "amount": 3})
                            self._scroll_accum = 0.0
                            self.last_action = f"scroll_{direction}"
                    self._last_index_y = ny
                else:
                    self._last_index_y = None
                    self._scroll_accum = 0.0

                self._was_pinch = pinch
            else:
                self._reset_edges()

            # Trail: always updated while we have a confident hand
            self._push_trail(self._cursor_x, self._cursor_y, now)
            self._expire_trail(now)

            return self._publish(now, active=active)

    # ── FSM ──

    def _advance_fsm(self, now: float, fist: bool, pinch: bool, open_palm: bool):
        if fist:
            if self.state == _State.IDLE:
                self._fist_since = now
                self.state = _State.ARMED
            elif self.state == _State.ARMED:
                if now - self._fist_since >= self.engage_hold:
                    self.state = _State.ENGAGED
                    self._burst_queue.append({"x": self._cursor_x,
                                              "y": self._cursor_y,
                                              "kind": "engage"})
            elif self.state == _State.COOLDOWN:
                # re-engage fast if fist comes back within grace
                self.state = _State.ENGAGED
            self._no_fist_since = now
        else:
            if self.state == _State.ENGAGED:
                if now - self._no_fist_since >= self.disengage_grace:
                    self.state = _State.IDLE
                    self._reset_edges()
            elif self.state == _State.ARMED:
                # never confirmed -> back to idle
                self.state = _State.IDLE
            elif self.state == _State.COOLDOWN:
                if now - self._no_fist_since >= self.disengage_grace:
                    self.state = _State.IDLE

    def _reset_edges(self):
        self._was_pinch = False
        self._was_dragging = False
        self._last_index_y = None
        self._scroll_accum = 0.0

    # ── action dispatch ──

    @staticmethod
    def _to_pixel(norm: float, span: int) -> int:
        return int(round(max(0.0, min(1.0, norm)) * (span - 1)))

    def _do(self, tool_name: str, args: dict):
        try:
            from tools import execute_tool
            execute_tool(tool_name, args)
        except Exception as e:
            print(f"[GestureCtrl] {tool_name} failed: {e}")

    def _do_drag(self, down: bool):
        try:
            import pyautogui
            if down:
                pyautogui.mouseDown(button="left")
            else:
                pyautogui.mouseUp(button="left")
        except Exception as e:
            print(f"[GestureCtrl] drag {'down' if down else 'up'} failed: {e}")

    # ── trail / burst bookkeeping ──

    def _push_trail(self, x: float, y: float, now: float):
        self._trail.append({"x": x, "y": y, "t": now})
        if len(self._trail) > self.trail_max:
            self._trail = self._trail[-self.trail_max:]

    def _expire_trail(self, now: float):
        self._trail = [p for p in self._trail if now - p["t"] <= self.trail_ttl]

    # ── publish ──

    def _publish(self, now: float, active: bool) -> dict:
        bursts = self._burst_queue
        self._burst_queue = []
        # age trail points 0..1 for opacity
        trail_out = []
        for p in self._trail:
            age = max(0.0, 1.0 - (now - p["t"]) / self.trail_ttl)
            trail_out.append({"x": round(p["x"], 4), "y": round(p["y"], 4), "a": round(age, 3)})
        return {
            "engaged": self.state == _State.ENGAGED,
            "armed": self.state == _State.ARMED,
            "state": self.state,
            "active": active,
            "cursor_x": round(self._cursor_x, 4),
            "cursor_y": round(self._cursor_y, 4),
            "screen_x": self._to_pixel(self._cursor_x, self._screen_w),
            "screen_y": self._to_pixel(self._cursor_y, self._screen_h),
            "action": self.last_action,
            "trail": trail_out,
            "bursts": bursts,
            "ts": round(now, 3),
        }


# ── Singleton ──────────────────────────────────────────────

_controller: GestureController | None = None


def get_controller() -> GestureController:
    global _controller
    if _controller is None:
        _controller = GestureController()
        try:
            import pyautogui
            size = pyautogui.size()
            _controller.configure_screen(size.width, size.height)
        except Exception as e:
            print(f"[GestureCtrl] screen probe failed: {e}")
    return _controller
