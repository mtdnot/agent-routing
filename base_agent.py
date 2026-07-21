"""
DNS型エージェントルーティング - Agent Base
"""
from __future__ import annotations
import json
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from uvicorn import Config, Server

logging.basicConfig(level=logging.INFO, format="%(name)s  %(message)s")
log = logging.getLogger("agent")

class Capability(BaseModel):
    prefix: str
    type: str = "authoritative"

class RoutingEntry(BaseModel):
    target: str
    confidence: float = 0.5
    success: int = 0
    fail: int = 0
    last_updated: float = 0.0

class Message(BaseModel):
    type: str = "query"
    sender: str
    recipient: str
    query: str = ""
    text: str = ""
    ttl: int = 5
    provenance: list[dict] = Field(default_factory=list)
    forwarded_to: str = ""

class Agent:
    def __init__(self, agent_id: str, port: int, capabilities: list[dict] | None = None,
                 acquaintances: dict[str, str] | None = None, host: str = "127.0.0.1",
                 llm_model: str = "deepseek-v4-flash"):
        self.id = agent_id
        self.port = port
        self.host = host
        self.llm_model = llm_model
        self.capabilities = [Capability(**c) for c in (capabilities or [])]
        self.routing_table: dict[str, RoutingEntry] = {}
        self.acquaintances: dict[str, str] = {}
        if acquaintances:
            for name, url in acquaintances.items():
                self.acquaintances[name] = url.rstrip("/")
        self.knowledge: dict[str, str] = {}
        self._seq = 0
        self.query_log: list[dict] = []  # クエリ処理履歴

        self.app = FastAPI(title=f"Agent {agent_id}")
        self.app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
        self._setup_routes()

    def know(self, topic: str, content: str):
        self.knowledge[topic] = content

    def add_acquaintance(self, name: str, base_url: str):
        self.acquaintances[name] = base_url.rstrip("/")

    def add_route(self, prefix: str, target: str, confidence: float = 0.5):
        self.routing_table[prefix] = RoutingEntry(target=target, confidence=confidence)

    def _log_query(self, query: str, action: str, detail: str = "", result: str = ""):
        self.query_log.insert(0, {
            "time": time.strftime("%H:%M:%S"),
            "query": query[:60],
            "action": action,
            "detail": detail[:80],
            "result": result[:150],
        })
        self.query_log = self.query_log[:50]

    def match_capability(self, query: str) -> bool:
        for cap in self.capabilities:
            if query.startswith(cap.prefix):
                return True
        return False

    def match_routing_table(self, query: str) -> Optional[RoutingEntry]:
        matched = None; matched_len = 0
        for prefix, entry in self.routing_table.items():
            if query.startswith(prefix) and len(prefix) > matched_len:
                matched = entry; matched_len = len(prefix)
        return matched

    def update_confidence(self, prefix: str, success: bool, target: str = ""):
        entry = self.routing_table.get(prefix)
        if not entry:
            if success and target:
                self.routing_table[prefix] = RoutingEntry(target=target, confidence=0.6, success=1, fail=0, last_updated=time.time())
            return
        if success:
            entry.success += 1
            entry.confidence = min(0.99, (entry.success + 1) / (entry.success + entry.fail + 2))
        else:
            entry.fail += 1
            entry.confidence = max(0.01, (entry.success + 1) / (entry.success + entry.fail + 2))
        entry.last_updated = time.time()

    def ask_llm(self, query: str) -> str:
        """LiteLLM経由でopencode-goに問い合わせ"""
        api_key = os.environ.get("OPENCODE_API_KEY", "")
        if not api_key:
            return f"[{self.id}] LLM not configured (set OPENCODE_API_KEY)"
        try:
            from litellm import completion
            resp = completion(
                model=f"openai/{self.llm_model}",
                api_base="https://opencode.ai/zen/go/v1",
                api_key=api_key,
                messages=[{
                    "role": "system",
                    "content": f"あなたは{self.id}という名前のAIエージェントです。与えられたクエリに対して簡潔に回答してください。"
                }, {
                    "role": "user",
                    "content": query
                }],
                max_tokens=300,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            log.warning(f"  LLM error: {e}")
            return f"[{self.id}] LLM応答失敗: {e}"

    def handle_query(self, msg: Message) -> dict:
        log.info(f"[{self.id}] << query '{msg.query[:50]}' from {msg.sender} (ttl={msg.ttl})")

        if msg.ttl <= 0:
            self._log_query(msg.query, "TTL_EXPIRED", f"ttl=0 from {msg.sender}")
            return {"type": "error", "text": "TTL expired", "sender": self.id}

        # 1. hardcoded knowledge
        for topic, content in self.knowledge.items():
            if msg.query.startswith(topic):
                self._log_query(msg.query, "KNOWLEDGE_HIT", f"topic={topic}")
                return {"type": "response", "sender": self.id, "text": content,
                        "provenance": msg.provenance + [{"agent": self.id, "role": "author"}], "query": msg.query}

        # 2. LLM (capability match)
        if self.match_capability(msg.query):
            self._log_query(msg.query, "LLM_CALL", f"capability match")
            text = self.ask_llm(msg.query)
            self._log_query(msg.query, "LLM_RESPONSE", result=text[:60])
            return {"type": "response", "sender": self.id, "text": text,
                    "provenance": msg.provenance + [{"agent": self.id, "role": "author"}], "query": msg.query}

        # 3. routing table
        entry = self.match_routing_table(msg.query)
        if entry and entry.target in self.acquaintances:
            target_url = self.acquaintances[entry.target]
            fm = msg.model_copy(deep=True)
            fm.ttl -= 1; fm.provenance = msg.provenance + [{"agent": self.id, "role": "forward"}]
            fm.recipient = entry.target; fm.sender = self.id
            try:
                resp = httpx.post(f"{target_url}/a2a/message", json=fm.model_dump(), timeout=15.0)
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("type") == "response":
                        self.update_confidence(msg.query, True, target=entry.target)
                        self._log_query(msg.query, "ROUTED", f"→ {entry.target} (conf={entry.confidence:.2f})", result.get("text","")[:60])
                        return {"type": "response", "sender": entry.target, "text": result.get("text",""),
                                "provenance": result.get("provenance",[]), "query": msg.query}
                    self.update_confidence(msg.query, False, target=entry.target)
                else:
                    self.update_confidence(msg.query, False, target=entry.target)
            except Exception as e:
                self.update_confidence(msg.query, False, target=entry.target)
                log.warning(f"  route fail: {e}")

        # 4. broadcast
        for name, url in self.acquaintances.items():
            if name == msg.sender or name == self.id: continue
            fm = msg.model_copy(deep=True)
            fm.ttl = msg.ttl - 1; fm.provenance = msg.provenance + [{"agent": self.id, "role": "forward"}]
            fm.recipient = name; fm.sender = self.id; fm.type = "forward"
            try:
                resp = httpx.post(f"{url}/a2a/message", json=fm.model_dump(), timeout=15.0)
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("type") == "response":
                        self.update_confidence(msg.query, True, target=name)
                        self._log_query(msg.query, "BROADCAST_OK", f"via {name}", result.get("text","")[:60])
                        return {"type": "response", "sender": name, "text": result.get("text",""),
                                "provenance": result.get("provenance",[]), "query": msg.query}
            except Exception:
                pass

        self._log_query(msg.query, "NOT_FOUND")
        return {"type": "error", "text": "not found", "sender": self.id, "query": msg.query}

    def _setup_routes(self):
        @self.app.get("/health")
        def health():
            return {
                "agent_id": self.id,
                "capabilities": [c.prefix for c in self.capabilities],
                "routing_table": {k: {"target": v.target, "confidence": round(v.confidence, 3),
                                       "success": v.success, "fail": v.fail}
                                  for k, v in self.routing_table.items()},
                "acquaintances": list(self.acquaintances.keys()),
                "knowledge": list(self.knowledge.keys()),
            }

        @self.app.get("/query_log")
        def get_query_log(limit: int = 20):
            return {"agent": self.id, "log": self.query_log[:limit]}

        @self.app.post("/a2a/message")
        def receive_message(msg: Message):
            if msg.type in ("query", "forward"):
                return self.handle_query(msg)
            return {"type": "error", "text": f"unknown type: {msg.type}"}

    def run(self):
        log.info(f"Starting agent [{self.id}] on {self.host}:{self.port}")
        Server(Config(app=self.app, host=self.host, port=self.port, log_level="error")).run()
