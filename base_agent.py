"""
DNS型エージェントルーティング - Agent Base
各エージェントのベースとなるクラスとFastAPIアプリケーション。
"""
from __future__ import annotations
import json
import logging
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from uvicorn import Config, Server

logging.basicConfig(level=logging.INFO, format="%(name)s  %(message)s")
log = logging.getLogger("agent")

# ── メッセージ型 ──────────────────────────────────────────────

class Capability(BaseModel):
    prefix: str
    type: str = "authoritative"  # authoritative | referral

class RoutingEntry(BaseModel):
    target: str
    confidence: float = 0.5
    success: int = 0
    fail: int = 0
    last_updated: float = 0.0

class Message(BaseModel):
    type: str = "query"  # query | forward | response | broadcast
    sender: str
    recipient: str
    query: str = ""
    text: str = ""
    ttl: int = 5
    provenance: list[dict] = Field(default_factory=list)
    forwarded_to: str = ""

# ── Agent Base ─────────────────────────────────────────────────

class Agent:
    def __init__(
        self,
        agent_id: str,
        port: int,
        capabilities: list[dict] | None = None,
        acquaintances: dict[str, str] | None = None,
        host: str = "127.0.0.1",
    ):
        self.id = agent_id
        self.port = port
        self.host = host
        self.capabilities = [Capability(**c) for c in (capabilities or [])]
        self.routing_table: dict[str, RoutingEntry] = {}
        self.acquaintances: dict[str, str] = {}
        if acquaintances:
            for name, url in acquaintances.items():
                self.acquaintances[name] = url.rstrip("/")
        self.knowledge: dict[str, str] = {}
        self.pending_requests: dict[str, str] = {} # query_id -> sender
        self._seq = 0

        self.app = FastAPI(title=f"Agent {agent_id}")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._setup_routes()

    def _seq_id(self) -> str:
        self._seq += 1
        return f"{self.id}_{self._seq}_{int(time.time())}"

    def know(self, topic: str, content: str):
        """検証用：エージェントに知識を直接セット"""
        self.knowledge[topic] = content

    def add_acquaintance(self, name: str, base_url: str):
        self.acquaintances[name] = base_url.rstrip("/")

    def add_route(self, prefix: str, target: str, confidence: float = 0.5):
        self.routing_table[prefix] = RoutingEntry(target=target, confidence=confidence)

    # ── ルーティング ──

    def match_capability(self, query: str) -> bool:
        """自分のcapabilityにマッチするか"""
        for cap in self.capabilities:
            if query.startswith(cap.prefix):
                return True
        return False

    def match_routing_table(self, query: str) -> Optional[RoutingEntry]:
        """routing_tableからlongest-prefix match"""
        matched = None
        matched_len = 0
        for prefix, entry in self.routing_table.items():
            if query.startswith(prefix) and len(prefix) > matched_len:
                matched = entry
                matched_len = len(prefix)
        return matched

    def update_confidence(self, prefix: str, success: bool, target: str = ""):
        """Beta分布ベースのconfidence更新。新規エントリも作成。"""
        entry = self.routing_table.get(prefix)
        if not entry:
            if success and target:
                self.routing_table[prefix] = RoutingEntry(
                    target=target, confidence=0.6, success=1, fail=0,
                    last_updated=time.time()
                )
                log.info(f"  ✚ NEW route: {prefix} → {target} (confidence=0.600)")
            return
        if success:
            entry.success += 1
            entry.confidence = min(0.99, (entry.success + 1) / (entry.success + entry.fail + 2))
            log.info(f"  ✓ confidence UP: {prefix} → {entry.target} = {entry.confidence:.3f}")
        else:
            entry.fail += 1
            entry.confidence = max(0.01, (entry.success + 1) / (entry.success + entry.fail + 2))
            log.info(f"  ✗ confidence DOWN: {prefix} → {entry.target} = {entry.confidence:.3f}")
        entry.last_updated = time.time()

    # ── メッセージ処理 ──

    def handle_query(self, msg: Message) -> dict:
        log.info(f"[{self.id}] << query '{msg.query[:50]}' from {msg.sender} (ttl={msg.ttl})")

        if msg.ttl <= 0:
            log.warning(f"  TTL expired")
            return {"type": "error", "text": "TTL expired", "sender": self.id}

        # 1. 自分のknowledgeを確認
        for topic, content in self.knowledge.items():
            if msg.query.startswith(topic):
                log.info(f"  ✓ 自knowledgeヒット: {topic}")
                provenance = msg.provenance + [
                    {"agent": self.id, "role": "author"}
                ]
                return {
                    "type": "response",
                    "sender": self.id,
                    "recipient": msg.sender,
                    "text": content,
                    "provenance": provenance,
                    "query": msg.query,
                }

        # 2. 自分のcapabilityにマッチするか
        if self.match_capability(msg.query):
            # LLMで回答生成（後でLiteLLM連携）
            log.info(f"  capability match → LLMで回答生成（未実装、フォールバック）")
            provenance = msg.provenance + [
                {"agent": self.id, "role": "author"}
            ]
            return {
                "type": "response",
                "sender": self.id,
                "recipient": msg.sender,
                "text": f"[{self.id}] 回答: {msg.query} については自分の知識に基づいて答えます。",
                "provenance": provenance,
                "query": msg.query,
            }

        # 3. routing_tableから転送先を探す
        entry = self.match_routing_table(msg.query)
        if entry and entry.target in self.acquaintances:
            target_url = self.acquaintances[entry.target]
            log.info(f"  routing match: {msg.query} → {entry.target} (confidence={entry.confidence:.3f})")
            log.info(f"  forwarding to {entry.target} @ {target_url}")

            forward_msg = msg.model_copy(deep=True)
            forward_msg.ttl -= 1
            forward_msg.provenance = msg.provenance + [
                {"agent": self.id, "role": "forward"}
            ]
            forward_msg.recipient = entry.target
            forward_msg.sender = self.id

            try:
                resp = httpx.post(
                    f"{target_url}/a2a/message",
                    json=forward_msg.model_dump(),
                    timeout=10.0,
                )
                log.info(f"  {entry.target} HTTP {resp.status_code}")
                if resp.status_code == 200:
                    result = resp.json()
                    log.info(f"  {entry.target} result type: {result.get('type')}")
                    if result.get("type") == "response":
                        self.update_confidence(msg.query, True, target=entry.target)
                        log.info(f"  ✓ response from {entry.target}")
                        return {"type": "response", "sender": entry.target, "text": result.get("text", ""),
                                "provenance": result.get("provenance", []), "query": msg.query}
                    elif result.get("type") == "error":
                        log.warning(f"  {entry.target} returned error: {result.get('text')}")
                        self.update_confidence(msg.query, False, target=entry.target)
                else:
                    self.update_confidence(msg.query, False, target=entry.target)
                    log.warning(f"  {entry.target} returned HTTP {resp.status_code}")
            except Exception as e:
                self.update_confidence(msg.query, False, target=entry.target)
                log.warning(f"  {entry.target} unreachable: {e}")

        # 4. 知り合いにブロードキャスト
        log.info(f"  知り合いにbroadcast: {list(self.acquaintances.keys())}")
        for name, url in self.acquaintances.items():
            if name == msg.sender or name == self.id:
                continue
            forward_msg = msg.model_copy(deep=True)
            forward_msg.ttl = msg.ttl - 1
            forward_msg.provenance = msg.provenance + [
                {"agent": self.id, "role": "forward"}
            ]
            forward_msg.recipient = name
            forward_msg.sender = self.id
            forward_msg.type = "forward"
            log.info(f"  broadcasting to {name} @ {url} ttl={forward_msg.ttl}")
            try:
                resp = httpx.post(
                    f"{url}/a2a/message",
                    json=forward_msg.model_dump(),
                    timeout=10.0,
                )
                log.info(f"  {name} responded HTTP {resp.status_code}")
                if resp.status_code == 200:
                    result = resp.json()
                    log.info(f"  {name} result type: {result.get('type')}")
                    if result.get("type") == "response":
                        self.update_confidence(msg.query, True, target=name)
                        log.info(f"  ✓ response from {name} via broadcast")
                        return {"type": "response", "sender": name, "text": result.get("text", ""),
                                "provenance": result.get("provenance", []), "query": msg.query}
            except Exception as e:
                log.warning(f"  broadcast to {name} failed: {e}")

        log.warning(f"  ！誰も知らなかった")
        return {"type": "error", "text": "not found", "sender": self.id, "query": msg.query}

    # ── FastAPI Routes ──

    def _setup_routes(self):
        app = self.app

        @app.get("/health")
        def health():
            return {
                "agent_id": self.id,
                "capabilities": [c.prefix for c in self.capabilities],
                "routing_table": {k: {"target": v.target, "confidence": round(v.confidence, 3)}
                                  for k, v in self.routing_table.items()},
                "acquaintances": list(self.acquaintances.keys()),
                "knowledge": list(self.knowledge.keys()),
            }

        @app.post("/a2a/message")
        def receive_message(msg: Message):
            if msg.type == "query" or msg.type == "forward":
                result = self.handle_query(msg)
                return result
            return {"type": "error", "text": f"unknown message type: {msg.type}"}

    # ── 起動 ──

    def run(self):
        log.info(f"Starting agent [{self.id}] on port {self.port}")
        config = Config(app=self.app, host=self.host, port=self.port, log_level="error")
        server = Server(config)
        server.run()
