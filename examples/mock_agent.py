"""Synthetic deterministic simulator for AgentLoad tests. Not an AI agent."""
import asyncio, os
from fastapi import FastAPI, Response

app = FastAPI(title="AgentLoad synthetic simulator")
_active = 0

@app.get('/health')
async def health(): return {'status': 'ok', 'simulator': True}

@app.post('/agent')
async def agent(body: dict, response: Response):
    global _active
    mode = body.get('mode', os.getenv('AGENTLOAD_SIMULATOR_MODE', 'concurrency_degradation'))
    threshold = int(os.getenv('AGENTLOAD_SIMULATOR_FAIL_AT', '4'))
    delay = float(os.getenv('AGENTLOAD_SIMULATOR_DELAY_SECONDS', '.03'))
    _active += 1
    try:
        await asyncio.sleep(delay)
        if mode == 'http_429': response.status_code = 429; return {'success': False}
        if mode == 'timeout': await asyncio.sleep(delay * 20)
        failed = mode == 'semantic_failure' or (mode == 'concurrency_degradation' and _active >= threshold)
        loop = 6 if mode == 'loop_limit' else 1
        return {'success': not failed, 'input_tokens': 10, 'output_tokens': 5, 'estimated_cost_usd': .001, 'tool_calls': ['lookup'] * loop, 'loop_depth': loop}
    finally:
        _active -= 1
