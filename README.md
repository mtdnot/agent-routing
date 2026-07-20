# DNS型エージェントルーティング

完全分散P2P方式のエージェント間ルーティング検証プロジェクト。

## 概要

DNS（Domain Name System）のアイデアを応用し、中央レジストリなしでエージェント同士が「誰が何を知っているか」を名前解決しながら情報をやり取りする仕組み。

各エージェントはネットワークの部分的な俯瞰（ルーティングテーブル）だけを持ち、不足は周りのエージェントに問い合わせる。成功/失敗に応じてconfidence（確信度）を学習する。

## クイックスタート

```bash
# 仮想環境
uv venv agent-routing-venv --python 3.13
source agent-routing-venv/bin/activate
uv pip install "fastapi>=0.115" "uvicorn[standard]>=0.34" "httpx>=0.28" "pydantic>=2.0"

# エージェント起動（3つのターミナルで）
python3 agent_c.py   # 知識エージェント（秘密情報Xを保持）
python3 agent_b.py   # 中継エージェント（AとCを接続）
python3 agent_a.py   # クエリ発行エージェント

# ダッシュボードを開く
open dashboard.html
```

## 検証テスト

```bash
python3 test_scenario.py
```

## アーキテクチャ

- エージェント間通信: HTTP/REST（各エージェントが独立ポートで待受）
- ルーティング: longest-prefix match + ブロードキャスト
- 学習: Beta分布ベースのconfidence更新
- プロトコル: A2Aライクなメッセージ形式（query/forward/response）

## Phase 0（完了 ✅）

- [x] 3エージェント（A, B, C）による基本ルーティング
- [x] 未学習→broadcast→学習→直接ルーティングのサイクル
- [x] Beta分布によるconfidence更新
- [x] Webダッシュボード

## Phase 1（TODO）

- [ ] LiteLLM連携（opencode-go）
- [ ] 出典チェーン（Provenance Chain）
- [ ] エージェント追加（D, E）
- [ ] ループ検出
- [ ] 可視化の充実
