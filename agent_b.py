#!/usr/bin/env python3
"""エージェントB: 中継エージェント"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_agent import Agent

agent = Agent(
    agent_id="B", port=8002, host="0.0.0.0",
    capabilities=[
        {"prefix": "knowledge/common/", "type": "authoritative"},
        {"prefix": "knowledge/general/", "type": "authoritative"},
    ],
    acquaintances={"A": "http://127.0.0.1:8001", "C": "http://127.0.0.1:8003"},
    llm_model="deepseek-v4-flash",
)

agent.add_route("knowledge/kuma/", "C", confidence=0.6)
agent.add_route("knowledge/secrets/", "C", confidence=0.5)

print(f"B起動 (知り合い: {list(agent.acquaintances.keys())}, routes: {len(agent.routing_table)})")
agent.run()
