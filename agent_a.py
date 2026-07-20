#!/usr/bin/env python3
"""エージェントA: クエリ発行エージェント（最初は何も知らない）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from base_agent import Agent

agent = Agent(
    agent_id="A",
    port=8001,
    host="0.0.0.0",
    capabilities=[
        {"prefix": "knowledge/mtdnot/", "type": "authoritative"},
    ],
    acquaintances={
        "B": "http://127.0.0.1:8002",
    },
)

print(f"エージェントA起動（知り合い: {list(agent.acquaintances.keys())}）")

# Serve dashboard from agent A
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
_dash_path = os.path.join(_script_dir, "dashboard.html")

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

if os.path.exists(_dash_path):
    @agent.app.get("/", response_class=HTMLResponse)
    def dashboard():
        with open(_dash_path) as f:
            return f.read()

agent.run()
