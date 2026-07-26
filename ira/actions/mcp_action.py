"""
actions/mcp_action.py — Action Converter for IRA MCP & Composio Client
"""

import mcp_client

def mcp_action(parameters: dict, player=None) -> str:
    action = parameters.get("action", "list").lower().strip()
    server_name = parameters.get("server_name", "")
    command = parameters.get("command", "")
    args = parameters.get("args", {})
    
    if action == "connect":
        return mcp_client.mcp_connect(server_name, command, args)
    elif action == "disconnect":
        return mcp_client.mcp_disconnect(server_name)
    elif action == "list":
        return mcp_client.mcp_list_servers()
    elif action == "composio_connect":
        return mcp_client.composio_connect(parameters.get("api_key", ""))
    else:
        return f"Unknown MCP action: {action}"
