"""
actions/change_avatar_expression.py — Tool action to dynamically trigger avatar expression states.
"""

_global_bridge = None


def register_hud_bridge(bridge):
    global _global_bridge
    _global_bridge = bridge


def change_avatar_expression_action(parameters: dict, player=None, speak=None) -> str:
    """
    Action handler to change IRA avatar expression.
    
    Parameters:
        expression: Expression state e.g. normal | happy | thinking | talking | sad | angry | giggling | smirking | shocked | facepalm
    """
    expression = parameters.get("expression", "normal").lower().strip()
    duration = parameters.get("duration", 4)
    try:
        duration = int(duration)
    except Exception:
        duration = 4

    global _global_bridge
    if _global_bridge:
        _global_bridge.setAvatarExpression(expression, duration)
        if player and hasattr(player, "write_log"):
            player.write_log(f"AVATAR: Expression changed to '{expression}' ({duration}s)")
        return f"Avatar expression changed to '{expression}' for {duration} seconds."
    
    return f"Notice: Avatar expression set to '{expression}' (HUD bridge offline)."
