#!/usr/bin/env python3
"""
drama-gateway-config.py — 把 DramaClaw CE 的模型网关指向本地 drama-gateway (:8790)。

原理：CE 的网关配置存在 settings.db 的 runtime_settings 表（SQLite），
Custom mode 读 custom_newapi_base_url + custom_newapi_api_key。
我们直接写这俩 key + model_gateway_mode=custom，零上游代码改动。

用法:
  python drama-gateway-config.py [--base http://127.0.0.1:8790/v1] [--key dummy]
  python drama-gateway-config.py --status   # 查看当前配置
  python drama-gateway-config.py --reset    # 回到 official 模式（默认网关）
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

STATE_DIR = Path(os.environ.get("NOVELVIDEO_STATE_DIR", "~/.hermes/drama-gateway/state")).expanduser()
# 实际 settings.db 路径：DramaClaw 的 state/local/settings.db
DB_CANDIDATES = [
    Path("~/Code/drama-claw/state/local/settings.db").expanduser(),
    Path(os.environ.get("DC_STATE", "~/Code/drama-claw/state")).expanduser() / "local" / "settings.db",
]

MODE_CUSTOM = "custom"
MODE_OFFICIAL = "official"
DEFAULT_BASE = "http://127.0.0.1:8790/v1"
DUMMY_KEY = "drama-gateway-local"


def find_db() -> Optional[Path]:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    return None


def connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runtime_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    return conn


def set_many(conn: sqlite3.Connection, values: dict[str, str]):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for k, v in values.items():
            conn.execute(
                """INSERT INTO runtime_settings(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (k, str(v), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def read_all(conn: sqlite3.Connection) -> dict[str, str]:
    return {str(r["key"]): str(r["value"]) for r in conn.execute("SELECT key, value FROM runtime_settings")}


def main():
    ap = argparse.ArgumentParser(description="Point DramaClaw CE at the local drama-gateway")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--key", default=DUMMY_KEY)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    db = find_db()
    if not db:
        # 还没跑过 CE → 先创建
        db = DB_CANDIDATES[0]
        print(f"[drama-gateway-config] settings.db 不存在，将创建: {db}", file=sys.stderr)
    if db is None:
        sys.exit("无法确定 settings.db 路径")

    conn = connect(db)
    if args.status:
        rows = read_all(conn)
        mode = rows.get("model_gateway_mode", "(unset)")
        base = rows.get("custom_newapi_base_url", "")
        key = rows.get("custom_newapi_api_key", "")
        print(f"mode: {mode}")
        print(f"custom_newapi_base_url: {base or '(unset)'}")
        print(f"custom_newapi_api_key: {('set' if key else '(unset)')}")
        conn.close()
        return

    if args.reset:
        set_many(conn, {"model_gateway_mode": MODE_OFFICIAL})
        print(f"[drama-gateway-config] 已切回 official 模式（RelayClaw 默认网关）")
        conn.close()
        return

    set_many(conn, {
        "model_gateway_mode": MODE_CUSTOM,
        "custom_newapi_base_url": args.base,
        "custom_newapi_api_key": args.key,
    })
    print(f"[drama-gateway-config] settings.db: {db}")
    print(f"  model_gateway_mode = {MODE_CUSTOM}")
    print(f"  custom_newapi_base_url = {args.base}")
    print(f"  custom_newapi_api_key = {args.key}")
    print("重启 DramaClaw 后生效 (ST_EDITION=ce uv run novelvideo api --port 8780)")
    conn.close()


if __name__ == "__main__":
    main()
