#!/usr/bin/env python3
"""エージェントC: 知識エージェント"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from base_agent import Agent

agent = Agent(
    agent_id="C", port=8003, host="0.0.0.0",
    capabilities=[
        {"prefix": "knowledge/secrets/", "type": "authoritative"},
        {"prefix": "knowledge/kuma/", "type": "authoritative"},
    ],
    acquaintances={"B": "http://127.0.0.1:8002"},
    llm_model="qwen3.7-plus",
)

agent.know("knowledge/kuma/secrets/meeting_20260720",
    "2026年7月20日MTG。議題: DNS型エージェントルーティングの検証設計。"
    "結論: Supernodeなしの完全分散P2P方式で進める。次回: 7/27 10:00")

agent.know("knowledge/secrets/password",
    "ルーターのパスワードは Cyc1eTr33_2026")

print(f"C起動 (knowledge: {list(agent.knowledge.keys())}, capabilities: {[c.prefix for c in agent.capabilities]})")
agent.run()
