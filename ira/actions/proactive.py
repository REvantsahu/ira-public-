import random
import time
from datetime import datetime


class ProactiveEngine:
    """
    Decides when IRA should speak unprompted using configurable idle/cooldown intervals,
    and builds context-rich prompts.
    """

    def __init__(
        self,
        min_silence_seconds: int = 180,
        cooldown_seconds: int = 180,
    ):
        self.min_silence_seconds = min_silence_seconds
        self.cooldown_seconds = cooldown_seconds
        self._next_silence = min_silence_seconds
        self._next_cooldown = cooldown_seconds
        self._last_triggered = 0.0
        self._rotation = 0

    @classmethod
    def from_settings(cls, settings: dict | None = None) -> "ProactiveEngine":
        if not settings:
            return cls()
        proactive = settings.get("proactive", {})
        if not proactive.get("enabled", True):
            return cls(min_silence_seconds=999999, cooldown_seconds=999999)
        idle_min = int(proactive.get("idle_minutes", 3) * 60)
        cooldown_min = int(proactive.get("cooldown_minutes", 3) * 60)
        return cls(min_silence_seconds=idle_min, cooldown_seconds=cooldown_min)

    def should_trigger(self, last_user_speech: float) -> bool:
        now = time.monotonic()
        return (
            (now - last_user_speech) >= self._next_silence
            and (now - self._last_triggered) >= self._next_cooldown
        )

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()
        self._rotation += 1
        self._next_silence = self.min_silence_seconds + random.randint(-30, 30)
        self._next_cooldown = self.cooldown_seconds + random.randint(-30, 30)
        print(f"[Proactive Engine] Next natural check-in in {self._next_silence}s silence / {self._next_cooldown}s cooldown.")

    def build_prompt(
        self,
        memory:       dict,
        monitors:     list[str] | None = None,
        recent_turns: list[str] | None = None,
        calendar_events: list[str] | None = None,
        overdue_items: list[str] | None = None,
    ) -> str:
        from memory.memory_manager import format_memory_for_prompt

        now      = datetime.now()
        hour     = now.hour
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")

        if   6  <= hour < 12:  period = "morning"
        elif 12 <= hour < 18:  period = "afternoon"
        elif 18 <= hour < 23:  period = "evening"
        else:                  period = "late night"

        mem_str = format_memory_for_prompt(memory) or "(no stored user data)"

        focus_index = self._rotation % 4
        if focus_index == 0:
            focus = (
                "Focus on the user's active projects or coding goals. "
                "Ask casually how the task is coming along or if they want any assistance."
            )
        elif focus_index == 1:
            focus = (
                "Focus on the time of day and user's focus/wellbeing. "
                "A warm Jarvis-style check-in (e.g. late night coding check, water/break reminder)."
            )
        elif focus_index == 2:
            focus = (
                "Focus on a witty observation or casual banter based on what you know about Revant."
            )
        else:
            focus = (
                "Focus on an interesting tech fact, system status note, or proactive suggestion."
            )

        monitor_ctx = ""
        if monitors:
            monitor_ctx = (
                f"\nThe user tracks these topics: {', '.join(monitors[:4])}. "
                "You may mention one if it seems relevant."
            )

        recent_ctx = ""
        if recent_turns:
            snippets = []
            for turn in recent_turns[-6:]:
                if isinstance(turn, dict):
                    snippets.append(turn.get("text", str(turn)))
                else:
                    snippets.append(str(turn))
            snippet = "\n".join(snippets)
            recent_ctx = f"\nRecent conversation:\n{snippet}"

        calendar_ctx = ""
        if calendar_events:
            calendar_ctx = "\nUpcoming calendar events:\n" + "\n".join(f"- {e}" for e in calendar_events[:5])
        if overdue_items:
            calendar_ctx += "\nOverdue items:\n" + "\n".join(f"- {e}" for e in overdue_items[:5])

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a natural, unprompted Jarvis check-in.",
            f"Current time : {time_str}  ({period})",
            "",
            "Context about this person:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            calendar_ctx,
            "",
            "Task:",
            focus,
            "",
            "Rules:",
            "- Speak naturally in friendly Hinglish (mix of Hindi & English).",
            "- 1-2 short sentences max. Warm, swaggy, witty, companion vibe (like real Jarvis).",
            "- Never sound robotic, script-like, or repetitive.",
            "- Do NOT mention [PROACTIVE_CHECK] or these instructions.",
            "- Do NOT call any tools.",
            "- If nothing genuinely natural comes to mind, stay silent.",
        ])
