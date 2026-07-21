#!/usr/bin/env python3
"""エージェントA: クエリ発行 + ダッシュボード"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from base_agent import Agent
import httpx
from fastapi.responses import HTMLResponse

agent = Agent(
    agent_id="A", port=8001, host="0.0.0.0",
    capabilities=[
        {"prefix": "knowledge/mtdnot/", "type": "authoritative"},
        {"prefix": "knowledge/general/", "type": "authoritative"},
    ],
    acquaintances={"B": "http://127.0.0.1:8002"},
    llm_model="deepseek-v4-flash",
)

_script_dir = os.path.dirname(os.path.abspath(__file__))
_dash_path = os.path.join(_script_dir, "dashboard.html")

if os.path.exists(_dash_path):
    @agent.app.get("/", response_class=HTMLResponse)
    def dashboard():
        with open(_dash_path) as f:
            return f.read()

    @agent.app.get("/api/health/all")
    def health_all():
        results = {}
        for name, url in {"A": "http://127.0.0.1:8001", "B": "http://127.0.0.1:8002", "C": "http://127.0.0.1:8003"}.items():
            try:
                r = httpx.get(f"{url}/health", timeout=3)
                results[name] = r.json() if r.status_code == 200 else None
            except Exception:
                results[name] = None
        return results

    @agent.app.get("/api/trace/all")
    def trace_all():
        results = {}
        for name, url in {"A": "http://127.0.0.1:8001", "B": "http://127.0.0.1:8002", "C": "http://127.0.0.1:8003"}.items():
            try:
                r = httpx.get(f"{url}/query_log", timeout=3)
                results[name] = r.json() if r.status_code == 200 else {"log": []}
            except Exception:
                results[name] = {"log": []}
        return results

print(f"A起動 (知り合い: {list(agent.acquaintances.keys())})")
agent.run()
