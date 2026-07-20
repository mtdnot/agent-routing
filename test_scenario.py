#!/usr/bin/env python3
"""DNS型エージェントルーティング - 検証テスト
エージェントA→B→Cの転送をテストする。
"""
import json
import sys
import time
import httpx
import subprocess
import signal
import os

BASE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(BASE, "..", "agent-routing-venv", "bin", "python3")
PYTHON = VENV if os.path.exists(VENV) else sys.executable

agents: list[subprocess.Popen] = []

def start_agent(name: str, port: int) -> subprocess.Popen:
    script = os.path.join(BASE, f"agent_{name}.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE + ":" + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [PYTHON, script],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=env, text=True,
    )
    agents.append(proc)
    # 起動待ち
    for _ in range(50):
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
            if r.status_code == 200:
                print(f"  ✓ {name} 起動 (port {port})")
                return proc
        except Exception:
            time.sleep(0.2)
    print(f"  ✗ {name} 起動失敗")
    return proc

def wait_for_agents(timeout=10):
    """全agentの起動完了を待つ"""
    deadline = time.time() + timeout
    ports = {"A": 8001, "B": 8002, "C": 8003}
    while time.time() < deadline:
        ready = []
        for name, port in ports.items():
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
                if r.status_code == 200:
                    ready.append(name)
            except Exception:
                pass
        if len(ready) == 3:
            return True
        time.sleep(0.3)
    return False

def send_query(sender: str, port: int, query: str) -> dict:
    """エージェントにクエリを送信"""
    msg = {
        "type": "query",
        "sender": sender,
        "recipient": sender,
        "query": query,
        "ttl": 5,
        "provenance": [{"agent": sender, "role": "request"}],
        "text": "",
        "forwarded_to": "",
    }
    resp = httpx.post(
        f"http://127.0.0.1:{port}/a2a/message",
        json=msg,
        timeout=15.0,
    )
    return resp.json()

def print_routing_table(port: int):
    r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
    data = r.json()
    print(f"    routing_table: {json.dumps(data.get('routing_table', {}), ensure_ascii=False, indent=6)}")

def main():
    print("=" * 60)
    print("DNS型エージェントルーティング 検証テスト")
    print("=" * 60)

    # 1. エージェント起動
    print("\n【1】エージェント起動")
    start_agent("a", 8001)
    start_agent("b", 8002)
    start_agent("c", 8003)

    if not wait_for_agents():
        print("✗ エージェント起動完了せず")
        cleanup()
        sys.exit(1)

    # Aの状態確認
    print("\n【2】初期状態確認")
    r = httpx.get("http://127.0.0.1:8001/health", timeout=3)
    a_state = r.json()
    print(f"  エージェントAのrouting_table: {a_state.get('routing_table', {})}")
    assert len(a_state["routing_table"]) == 0, "Aのrouting_tableは空であるべき"
    print("  ✓ Aは誰のことも知らない")

    # 3. クエリ発行
    print("\n【3】クエリ発行: knowledge/kuma/secrets/meeting_20260720")
    print("  A → （知らない）→ B → （routing）→ C")

    result = send_query("A", 8001, "knowledge/kuma/secrets/meeting_20260720")
    print(f"\n  結果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 4. 検証
    print("\n【4】検証")
    if result.get("text"):
        print(f"  ✓ 応答テキスト取得: {result['text'][:60]}...")
    else:
        print("  ✗ 応答テキストなし")
        cleanup()
        sys.exit(1)

    provenance = result.get("provenance", [])
    chain = [p["agent"] for p in provenance]
    print(f"  経路: {' → '.join(chain)}")
    if "A" in chain and "B" in chain and "C" in chain:
        print("  ✓ A→B→C の経路を通過した")
    else:
        print("  ✗ 期待した経路を通っていない")

    # 5. Aのrouting_tableが更新されたか
    print("\n【5】学習結果確認")
    r = httpx.get("http://127.0.0.1:8001/health", timeout=3)
    a_updated = r.json()
    if a_updated.get("routing_table"):
        print(f"  ✓ Aのrouting_tableが更新された:")
        print_routing_table(8001)
    else:
        print("  - Aのrouting_tableは更新されていない")

    # Bの状態
    r = httpx.get("http://127.0.0.1:8002/health", timeout=3)
    b_state = r.json()
    print(f"\n  Bのrouting_table:")
    print_routing_table(8002)

    print("\n" + "=" * 60)
    print("✓ 検証完了")
    print("=" * 60)

def cleanup():
    print("\nクリーンアップ...")
    for p in agents:
        p.terminate()
        try:
            p.wait(timeout=3)
        except Exception:
            p.kill()

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
