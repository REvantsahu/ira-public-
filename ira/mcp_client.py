"""IRA MCP Client — connect to MCP servers, discover & call tools.

MCP (Model Context Protocol) servers provide tools that IRA can use.
Supports SSE transport (for standard MCP servers) and StreamableHTTP (for Composio).
All MCP tools are converted to Gemini FunctionDeclaration format and merged
into IRA's tool list at runtime.
"""

from __future__ import annotations

import os
import json
import asyncio
import threading
from pathlib import Path

MCP_SERVERS_DIR = Path(__file__).parent / "mcp_servers"

_connected_servers: dict[str, dict] = {}
_lock = threading.Lock()


def _server_config_path(name: str) -> Path:
    return MCP_SERVERS_DIR / f"{name}.json"


def _ensure_dir():
    MCP_SERVERS_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# MCP Server Config Management (persist to JSON files)
# ═══════════════════════════════════════════════════════════════

def mcp_connect(name: str, url: str, headers: dict | None = None, transport: str = "streamable_http") -> str:
    _ensure_dir()
    cfg = {
        "name": name,
        "url": url,
        "headers": headers or {},
        "transport": transport,
    }
    path = _server_config_path(name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return f"MCP server '{name}' configured ({transport}) at {url}"


def mcp_disconnect(name: str) -> str:
    path = _server_config_path(name)
    if not path.exists():
        return f"MCP server '{name}' not found"
    os.remove(path)
    with _lock:
        _connected_servers.pop(name, None)
    return f"MCP server '{name}' disconnected and removed"


def mcp_list_servers() -> str:
    _ensure_dir()
    files = sorted(MCP_SERVERS_DIR.glob("*.json"))
    if not files:
        return "No MCP servers configured. Use mcp_connect to add one."
    lines = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            lines.append(f"  {cfg.get('name', path.stem)} — {cfg.get('transport', '?')} @ {cfg.get('url', '?')}")
        except Exception:
            lines.append(f"  {path.stem} — (invalid config)")
    return f"MCP Servers ({len(lines)}):\n" + "\n".join(lines)


def mcp_remove_tool(tool_name: str) -> str:
    """Remove a tool from discovery cache so Gemini stops suggesting it."""
    with _lock:
        for srv in _connected_servers.values():
            srv["tools"] = [t for t in srv.get("tools", []) if t["name"] != tool_name]
    return f"Tool '{tool_name}' removed from MCP tool cache"


# ═══════════════════════════════════════════════════════════════
# MCP Session Management (async → sync wrapper)
# ═══════════════════════════════════════════════════════════════

async def _create_session(url: str, headers: dict | None, transport: str):
    """Connect to an MCP server and return (session, tools_list)."""
    http_client = None
    if headers:
        import httpx
        http_client = httpx.AsyncClient(headers=headers)

    if transport == "streamable_http":
        from mcp.client.streamable_http import streamable_http_client
        transport_ctx = streamable_http_client(url, http_client=http_client)
    else:
        from mcp.client.sse import sse_client
        transport_ctx = sse_client(url=url, headers=headers)

    async with transport_ctx as streams:
        read, write = streams[0], streams[1]
        from mcp.client.session import ClientSession
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            tools_list = []
            for t in tools_result.tools:
                tools_list.append({
                    "name": f"mcp_{t.name}",
                    "original_name": t.name,
                    "description": t.description or "",
                    "inputSchema": t.inputSchema,
                })
            return tools_list


def _discover_worker(name: str, url: str, headers: dict | None, transport: str, results: list):
    """Thread worker to run async MCP discovery."""
    try:
        tools = asyncio.run(_create_session(url, headers, transport))
        with _lock:
            if name not in _connected_servers:
                _connected_servers[name] = {}
            _connected_servers[name].update({
                "url": url,
                "transport": transport,
                "tools": tools,
                "connected": True,
            })
        results.append({"name": name, "status": "ok", "count": len(tools)})
    except Exception as e:
        with _lock:
            if name not in _connected_servers:
                _connected_servers[name] = {}
            _connected_servers[name]["connected"] = False
            _connected_servers[name]["error"] = str(e)
        results.append({"name": name, "status": "error", "error": str(e)})


def discover_tools_for(name: str) -> str:
    """Discover tools from a configured MCP server. Connects, lists tools, caches them."""
    path = _server_config_path(name)
    if not path.exists():
        return f"MCP server '{name}' not configured. Use mcp_connect first."
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    results = []
    t = threading.Thread(
        target=_discover_worker,
        args=(cfg["name"], cfg["url"], cfg.get("headers"), cfg.get("transport", "streamable_http"), results),
        daemon=True,
    )
    t.start()
    t.join(timeout=15)

    if not results:
        return f"Timeout connecting to MCP server '{name}'"
    r = results[0]
    if r["status"] == "error":
        return f"Error connecting to '{name}': {r.get('error', 'unknown')}"
    return f"Discovered {r['count']} tools from '{name}'"


def discover_all_servers() -> list[dict]:
    """Discover tools from ALL configured MCP servers. Returns list of tool declarations."""
    _ensure_dir()
    all_tools = []
    files = sorted(MCP_SERVERS_DIR.glob("*.json"))
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            results = []
            t = threading.Thread(
                target=_discover_worker,
                args=(cfg["name"], cfg["url"], cfg.get("headers"), cfg.get("transport", "streamable_http"), results),
                daemon=True,
            )
            t.start()
            t.join(timeout=10)
            if results and results[0]["status"] == "ok":
                all_tools.extend(_connected_servers.get(cfg["name"], {}).get("tools", []))
        except Exception:
            pass
    return all_tools


def get_cached_tool_declarations() -> list[dict]:
    """Get all cached MCP tools as Gemini FunctionDeclaration-style dicts."""
    declarations = []
    with _lock:
        for srv_name, srv_data in _connected_servers.items():
            if not srv_data.get("connected"):
                continue
            for t in srv_data.get("tools", []):
                decl = {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": _convert_schema(t["inputSchema"]),
                    "_mcp_server": srv_name,
                    "_mcp_original_name": t["original_name"],
                }
                declarations.append(decl)
    return declarations


def _convert_schema(schema: dict) -> dict:
    """Convert JSON Schema to Gemini FunctionDeclaration parameters format."""
    if not schema:
        return {"type": "OBJECT", "properties": {}}
    result = {
        "type": schema.get("type", "OBJECT").upper(),
        "properties": {},
    }
    props = schema.get("properties", {})
    required = schema.get("required", [])
    for prop_name, prop_schema in props.items():
        prop_type = prop_schema.get("type", "STRING").upper()
        desc = prop_schema.get("description", "")
        p = {"type": prop_type, "description": desc}
        if "enum" in prop_schema:
            p["enum"] = prop_schema["enum"]
        if "items" in prop_schema:
            p["items"] = {"type": prop_schema["items"].get("type", "STRING").upper()}
        result["properties"][prop_name] = p
    if required:
        result["required"] = required
    return result


# ═══════════════════════════════════════════════════════════════
# MCP Tool Execution (sync wrapper)
# ═══════════════════════════════════════════════════════════════

async def _call_mcp_tool_async(server_name: str, tool_name: str, args: dict) -> str:
    """Connect, call tool, return result text."""
    path = _server_config_path(server_name)
    if not path.exists():
        return f"MCP server '{server_name}' not configured"
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    http_client = None
    headers = cfg.get("headers")
    if headers:
        import httpx
        http_client = httpx.AsyncClient(headers=headers)

    transport_type = cfg.get("transport", "streamable_http")
    if transport_type == "streamable_http":
        from mcp.client.streamable_http import streamable_http_client
        transport_ctx = streamable_http_client(cfg["url"], http_client=http_client)
    else:
        from mcp.client.sse import sse_client
        transport_ctx = sse_client(url=cfg["url"], headers=headers)

    async with transport_ctx as streams:
        read, write = streams[0], streams[1]
        from mcp.client.session import ClientSession
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, args)
            if result.isError:
                error_text = "; ".join(
                    c.text for c in result.content if hasattr(c, "text")
                ) or str(result)
                return f"Error calling {tool_name}: {error_text}"
            texts = []
            for c in result.content:
                if hasattr(c, "text"):
                    texts.append(c.text)
            return "\n".join(texts) if texts else "(no output)"


def call_tool(server_name: str, tool_name: str, args: dict) -> str:
    """Synchronously call an MCP tool by finding the right server and routing."""
    with _lock:
        for srv_name, srv_data in _connected_servers.items():
            for t in srv_data.get("tools", []):
                if t["name"] == tool_name:
                    original_name = t["original_name"]
                    found_server = srv_name
                    break
            else:
                continue
            break
        else:
            return f"Tool '{tool_name}' not found in any connected MCP server"

    try:
        return asyncio.run(_call_mcp_tool_async(found_server, original_name, args))
    except Exception as e:
        return f"MCP tool error ({tool_name}): {e}"


# ═══════════════════════════════════════════════════════════════
# Composio Integration — create session + get tools
# ═══════════════════════════════════════════════════════════════

def _get_active_toolkits(composio_client) -> list[str]:
    """Fetch active connected toolkit slugs from Composio."""
    try:
        active = []
        accounts = composio_client.connected_accounts.list(limit=100)
        for item in accounts.items:
            if item.status == "ACTIVE" and hasattr(item, "toolkit") and item.toolkit:
                active.append(item.toolkit.slug)
        return list(set(active))
    except Exception as e:
        print(f"[COMPOSIO] Error fetching active toolkits: {e}")
        return []


def composio_connect(api_key: str, user_id: str = "ira-user", toolkits: list | None = None) -> str:
    """Connect to Composio with API key. Sets up MCP endpoint for active tools only."""
    try:
        from composio import Composio
        composio_client = Composio(api_key=api_key)
        
        if toolkits is None:
            # Dynamically discover active toolkits
            active = _get_active_toolkits(composio_client)
            toolkits = active if active else ["gemini"]
            
        session = composio_client.create(user_id=user_id, toolkits=toolkits)
        mcp_url = session.mcp.url
        if not mcp_url:
            return "Composio session created but no MCP URL returned"
        return mcp_connect("composio", mcp_url, headers={"x-api-key": api_key}, transport="streamable_http")
    except ImportError:
        return "composio package not installed. Run: pip install composio"
    except Exception as e:
        return f"Composio error: {e}"


MCP_FUNCTIONS = {
    "mcp_connect": mcp_connect,
    "mcp_disconnect": mcp_disconnect,
    "mcp_list_servers": mcp_list_servers,
    "mcp_remove_tool": mcp_remove_tool,
}
