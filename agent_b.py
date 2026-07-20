#!/usr/bin/env python3
"""エージェントB: 中継エージェント（AとCを知っている）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from base_agent import Agent

agent = Agent(
    agent_id="B",
    port=8002,
    capabilities=[
        {"prefix": "knowledge/common/", "type": "authoritative"},
    ],
    acquaintances={
        "A": "http://127.0.0.1:8001",
        "C": "http://127.0.0.1:8003",
    },
)

# BはCがknowledge/kuma/を扱っていることをぼんやり知っている
agent.add_route("knowledge/kuma/", "C", confidence=0.6)
agent.add_route("knowledge/secrets/", "C", confidence=0.5)

# B自身の一般知識
agent.know("knowledge/common/greeting", "こんにちは！Bです")

print(f"エージェントB起動（知り合い: {list(agent.acquaintances.keys())}）")
agent.run()
