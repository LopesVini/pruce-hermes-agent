"""Synthetic Plow transport for isolated boot tests; never real accounts or LLMs."""
from aiohttp import web
from datetime import datetime, timezone

LINE = {"uid": "ln_fixture", "provider_type": "imessage", "provider_key": "+15550000000",
        "display_name": "Prucê", "agent_uid": "agent_fixture"}
OWNER = {"type": "member", "uid": "owner_fixture", "role": "owner",
         "display_name": "Fixture Owner", "provider_key": "+15550000001"}
CHAT = {"uid": "chat_fixture", "status": "active", "trusted": False,
        "line": LINE, "participants": [OWNER,
        {"type": "agent", "relationship": "self", "line": LINE}]}
state = {"ready": False, "calls": 0, "sockets": 0, "messages": [], "replies": []}
AGENT_CREATED_AT = datetime.now(timezone.utc).isoformat()


async def handle(request):
    path = request.path
    if path == "/fixture/status":
        return web.json_response(state)
    if path == "/fixture/create":
        state["ready"] = True
        data = await request.json()
        if data.get("first_message"):
            state["messages"] = [{"uid": "msg_first", "direction": "inbound", "sender": OWNER,
                "body": "/status", "attachments": [], "created_at": datetime.now(timezone.utc).isoformat()}]
        return web.json_response({"ok": True})
    if path == "/v1/agents/cloud/me":
        state["calls"] += 1
        return web.json_response({"line": LINE, "chats": [CHAT] if state["ready"] else [], "mcp_url": None})
    if path == "/v1/chats":
        return web.json_response({"data": [CHAT] if state["ready"] else [], "has_more": False})
    if path == "/v1/chats/chat_fixture":
        return web.json_response(CHAT)
    if path == "/v1/lines":
        return web.json_response({"data": [LINE], "has_more": False})
    if path == "/v1/auth/profile":
        return web.json_response({"referred_by": None})
    if path == "/v1/agents/me":
        return web.json_response({"line": LINE, "agent": {"uid": "agent_fixture", "created_at": AGENT_CREATED_AT,
            "settings": {"verbose_output": {"value": False}}}})
    if path == "/v1/ws/ticket":
        return web.json_response({"ticket": "offline-fixture-ticket"})
    if path == "/v1/ws":
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        state["sockets"] += 1
        await socket.send_json({"type": "connected"})
        async for _ in socket:
            pass
        return socket
    if path == "/v1/chats/chat_fixture/messages":
        if request.method == "GET":
            # A handled cursor bounds recovery after restart.
            messages = [] if request.query.get("before") == "msg_first" else state["messages"]
            return web.json_response({"data": messages, "has_more": False})
        body = await request.json()
        state["replies"].append(body)
        return web.json_response({"uid": "reply_fixture_" + str(len(state["replies"]))})
    if path == "/v1/chats/chat_fixture/typing":
        return web.json_response({"ok": True})
    # No inference service: the first inbound /status is handled by Hermes itself.
    return web.json_response({"error": "not implemented by offline fixture"}, status=404)


app = web.Application()
app.router.add_route("*", "/{path:.*}", handle)
web.run_app(app, host="0.0.0.0", port=8080, print=None, access_log=None)
