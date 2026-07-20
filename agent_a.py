#!/usr/bin/env python3
"""エージェントA: クエリ発行エージェント（最初は何も知らない）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from base_agent import Agent

agent = Agent(
    agent_id="A",
    port=8001,
    capabilities=[
        {"prefix": "knowledge/mtdnot/", "type": "authoritative"},
    ],
    acquaintances={
        "B": "http://127.0.0.1:8002",
    },
)

print(f"エージェントA起動（知り合い: {list(agent.acquaintances.keys())}）")
agent.run()
