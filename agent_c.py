#!/usr/bin/env python3
"""エージェントC: 知識エージェント（秘密情報Xを持つ）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from base_agent import Agent

agent = Agent(
    agent_id="C",
    port=8003,
    capabilities=[
        {"prefix": "knowledge/kuma/", "type": "authoritative"},
        {"prefix": "knowledge/secrets/", "type": "authoritative"},
    ],
    acquaintances={
        "B": "http://127.0.0.1:8002",
    },
)

agent.know("knowledge/kuma/secrets/meeting_20260720",
    "【会議内容】2026年7月20日、kumaとmtdnotのMTG。"
    "議題: DNS型エージェントルーティングの検証設計。"
    "結論: Supernodeなしの完全分散P2P方式でPhase0を進める。"
    "次回: 7/27 10:00"
)

agent.know("knowledge/secrets/password",
    "ルーターのパスワードは Cyc1eTr33_2026"
)

print(f"エージェントC起動（知識: {list(agent.knowledge.keys())}）")
agent.run()
