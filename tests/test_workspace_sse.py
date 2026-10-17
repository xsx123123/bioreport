import asyncio

from bioreport.sse import encode_event, operation_events


def test_sse_protocol_is_json_safe_and_terminal():
    encoded = encode_event("token", {"text": "line\nnext /tmp/private/result.csv"})
    assert "event: token" in encoded
    assert "\\n" in encoded
    assert "private" not in encoded
    async def collect():
        return [item async for item in operation_events([("started", {"operation_id": "x"}), ("completed", {"status": "ok"})])]
    output = asyncio.run(collect())
    assert output[-1].startswith("event: completed")


def test_sse_supports_tool_status_event():
    async def collect():
        return [item async for item in operation_events([
            ("started", {"operation_id": "x"}),
            ("tool_status", {"tool": "get_module_evidence", "status": "completed"}),
            ("completed", {"status": "ok"}),
        ])]
    output = asyncio.run(collect())
    assert any(item.startswith("event: tool_status") for item in output)
