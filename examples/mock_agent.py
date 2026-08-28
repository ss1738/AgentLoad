"""Deterministic AgentLoad simulator, not a real AI agent."""
import asyncio

from fastapi import FastAPI, Response

app = FastAPI(title="AgentLoad simulator")
_calls = 0
_active = 0

@app.post("/agent")
async def agent(_: dict, response: Response):
    global _calls, _active
    _calls += 1
    _active += 1
    try:
        # Higher overlap has deterministic latency, rate limiting, failed tasks, and loops.
        await asyncio.sleep(0.002 * _active)
        if _active > 20:
            response.status_code = 429
            return {"success": False, "input_tokens": 20, "output_tokens": 0, "estimated_cost_usd": .0002, "tool_calls": [], "loop_depth": 0}
        loop_depth = 6 if _active > 10 else 1
        success = _active <= 10 and _calls % 10 != 0
        return {"success": success, "input_tokens": 120, "output_tokens": 60,
                "estimated_cost_usd": .003, "tool_calls": ["lookup"] * loop_depth,
                "loop_depth": loop_depth}
    finally:
        _active -= 1
