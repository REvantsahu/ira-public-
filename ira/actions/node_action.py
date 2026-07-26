"""
actions/node_action.py — Action Converter for IRA Native QML Floating Windows / Desktop Nodes
Connects to IRA's native PySide6 QML Overlay (hud_overlay.py) to manage floating widgets on screen.
"""

import json

def node_action(parameters: dict, player=None) -> str:
    action = parameters.get("action", "create").lower().strip()
    node_id = parameters.get("node_id", "node_1")
    title = parameters.get("title", "IRA Node")
    content = parameters.get("content", "")
    x = parameters.get("x", 100)
    y = parameters.get("y", 100)
    width = parameters.get("width", 400)
    height = parameters.get("height", 300)
    
    payload = {
        "action": action,
        "id": node_id,
        "title": title,
        "content": content,
        "x": x,
        "y": y,
        "width": width,
        "height": height
    }

    try:
        from hud_overlay import get_active_bridge
        bridge = get_active_bridge()
        if bridge:
            bridge.nodeEventReceived.emit(json.dumps(payload))
            return f"Node action '{action}' executed for node '{title}' on HUD overlay."
    except Exception as e:
        print(f"[node_action] Bridge error: {e}")
        
    return f"Node action '{action}' recorded ({title})."
