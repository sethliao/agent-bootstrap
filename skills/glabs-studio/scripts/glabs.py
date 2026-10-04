#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""glabs.py — G-Labs Studio 原生 Webhook API 统一客户端（纯标准库）

为什么要有它（而不是继续走 drama-gateway :8790）：
  · gateway 是给 DramaClaw 用的 **OpenAI 兼容适配层**，只暴露 image/video/audio 三件事。
  · G-Labs 原生 API 有 **6 个生成端点**（image / video / grok / meta / openai / upscale），
    其中 **upscale 是本地 Real-ESRGAN、不耗 quota**，gateway 根本没接。
  · 只出图出片时少一跳，报错信息也是原生的，好排查。

设计铁律（都是踩过的坑）：
  ① **禁用代理**：本机 curl/urllib 会被 HTTP_PROXY 劫持，回环请求变 502
     `upstream connect failed: Connection refused (os error 61)`。本脚本用显式空代理 opener。
  ② **key 自动多路径解析**：app 改名（Automation → Studio）时 key 会重置，硬编码路径必挂。
  ③ **参考图默认走 base64**，不走 path —— app 读 ~/Documents 这类 TCC 保护目录会报
     `UPLOAD_ERROR Operation not permitted`；base64 让 app 完全不碰磁盘。
  ④ **`--dry-run` 先出 body 不提交**：烧 quota 前先看价目（Seth 的铁律）。

用法见 SKILL.md；`glabs.py --help` 也可。
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = os.environ.get("GLABS_BASE_URL", "http://127.0.0.1:8765")
HOME = pathlib.Path.home()

# key 的查找顺序（先到先用）。最后两项是 app 自己的配置文件 —— 唯一真源。
KEY_SOURCES = [
    ("env GLABS_API_KEY", lambda: os.environ.get("GLABS_API_KEY", "")),
    ("~/.hermes/.glabs_key", lambda: _read_text(HOME / ".hermes/.glabs_key")),
    ("G-Labs Studio/webhook_config.json", lambda: _read_json_key(
        HOME / "Library/Application Support/G-Labs Studio/webhook_config.json")),
    ("G-Labs Automation/webhook_config.json", lambda: _read_json_key(
        HOME / "Library/Application Support/G-Labs Automation/webhook_config.json")),
]

PROVIDERS_INI = HOME / ".hermes/drama-gateway/providers.ini"


# ─────────────────────────── 基础设施 ───────────────────────────

def _read_text(p: pathlib.Path) -> str:
    try:
        return p.read_text().strip()
    except Exception:
        return ""


def _read_json_key(p: pathlib.Path) -> str:
    try:
        return json.loads(p.read_text()).get("api_key", "")
    except Exception:
        return ""


def resolve_key(explicit: str = "") -> tuple[str, str]:
    """返回 (key, 来源说明)。"""
    if explicit:
        return explicit, "--key 参数"
    for label, fn in KEY_SOURCES:
        k = fn()
        if k:
            return k, label
    return "", "未找到"


def provider_account_id() -> str:
    """读 providers.ini 里钉的 account_id（**仅供兼容**，默认不再使用）。

    ⚠️ 2026-09-19：这个 id 是**改名前的旧快照**（`0d385969-…` 在新 app 的配置里根本不存在，
       它是旧 app `openai_accounts.json` 里的），带着它提交会 `Max Retries Exceeded`。
       新 app 自己管账号轮换（`flow_accounts.json` 里每号有 `_runtime_uuid`），
       所以**默认不传 account_id**，让 app 自己挑；要钉死用 `--account-id`。
    """
    try:
        for line in PROVIDERS_INI.read_text().splitlines():
            line = line.strip()
            if line.startswith("account_id") and "=" in line:
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def live_accounts() -> list:
    """读 app 当前的 Flow 账号池（排查用，只读）。"""
    p = HOME / "Library/Application Support/G-Labs Studio/flow_accounts.json"
    try:
        out = []
        for a in json.loads(p.read_text()):
            if isinstance(a, dict):
                out.append({
                    "email": a.get("email"), "status": a.get("status"),
                    "tier": a.get("tier"), "credits": a.get("credits"),
                    "uuid": a.get("_runtime_uuid"),
                    "enabled": a.get("enabled"),
                    "image": a.get("image_enabled"), "video": a.get("video_enabled"),
                    "last": a.get("last_request_status"),
                })
        return out
    except Exception:
        return []


def key_source_hint() -> str:
    """app 配置文件里 key 的实时真源（报错时提示用）。"""
    p = HOME / "Library/Application Support/G-Labs Studio/webhook_config.json"
    k = _read_json_key(p)
    return f"{p} → {k[:6]}…" if k else f"{p}（读不到）"


# 关键：空 ProxyHandler，绕开 HTTP_PROXY —— 见文件头铁律 ①
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(method: str, url: str, body: dict | None = None, key: str = "",
         timeout: int = 300, want_bytes: bool = False):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (raw if want_bytes else json.loads(raw.decode()))
    except urllib.error.HTTPError as e:
        raw = e.read()
        if want_bytes:
            raise
        try:
            return e.code, json.loads(raw.decode())
        except Exception:
            return e.code, {"error": raw.decode(errors="replace")[:400]}
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def to_data_url(path: str) -> str:
    """绝对路径 → data URL（base64）。app 不碰磁盘，绕开 TCC。"""
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise SystemExit(f"参考图不存在: {p}")
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def build_refs(paths, mode: str, field: str = "reference_images"):
    """参考图列表 → 原生 API 的引用格式。mode=base64(默认) | path"""
    if not paths:
        return {}
    if mode == "path":
        # path 形式仅当调用方与 app 同机有效；且 **不能放 TCC 保护目录**
        return {field: [{"path": str(pathlib.Path(p).expanduser()),
                         "name": os.path.basename(p)} for p in paths]}
    return {field: [to_data_url(p) for p in paths]}


def download(url: str, out_dir, name: str = "") -> str:
    out_dir = pathlib.Path(out_dir).expanduser()   # 容忍 str（调用方常常直接传字符串）
    out_dir.mkdir(parents=True, exist_ok=True)
    if not name:
        name = os.path.basename(urllib.parse.urlparse(url).path) or f"out_{int(time.time())}"
    dest = out_dir / name
    code, raw = http("GET", url, want_bytes=True, timeout=600)
    if code != 200:
        raise SystemExit(f"下载失败 {code}: {url}")
    dest.write_bytes(raw)
    return str(dest)


def _payload_summary(payload: dict) -> str:
    """干跑用的紧凑摘要 —— prompt 很长时也能一眼看到关键字段（模型 / 比例 / 参考图数量）。"""
    lines = []
    refs = payload.get("reference_images") or payload.get("images") or []
    for k, v in payload.items():
        if k in ("prompt", "reference_images", "images"):
            continue
        lines.append(f"  {k} = {json.dumps(v, ensure_ascii=False)}")
    lines.append(f"  reference_images = {len(refs)} 张")
    for i, r in enumerate(refs):
        s = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        lines.append(f"    [{i}] {s[:70]}{'…' if len(s) > 70 else ''} ({len(s)} chars)")
    p = payload.get("prompt") or ""
    lines.append(f"  prompt = {len(p)} chars，前 120 字：{p[:120]}…")
    return "\n".join(lines)


def submit(base: str, key: str, path: str, payload: dict, dry: bool) -> str:
    if dry:
        print("[dry-run] POST " + base + path)
        print(_payload_summary(payload))          # ← 关键字段摘要（不会被长 prompt 挤掉）
        print("--- 请求体（截断至 2500 字）---")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:2500])
        print("[dry-run] 未提交，零消耗。")
        raise SystemExit(0)
    code, resp = http("POST", base + path, payload, key=key, timeout=120)
    if code not in (200, 202):
        hint = ""
        if code == 401:
            hint = (f"\n  401 = key 失效。app 改名/重置会换 key。\n"
                    f"  当前真源: {key_source_hint()}\n"
                    f"  修法: 把 webhook_config.json 的 api_key 同步到 ~/.hermes/.glabs_key")
        raise SystemExit(f"提交失败 {code}: {json.dumps(resp, ensure_ascii=False)}{hint}")
    tid = resp.get("task_id") or ""
    print(f"已入队 task_id={tid} ({resp.get('status', '?')})")
    return tid


def wait(base: str, key: str, tid: str, timeout: int, quiet: bool = False) -> dict:
    t0, last = time.time(), ""
    while time.time() - t0 < timeout:
        code, s = http("GET", f"{base}/api/status/{tid}", key=key, timeout=30)
        st = str(s.get("status", "")).lower()
        if st != last and not quiet:
            print(f"  … {st or '?'}  ({time.time() - t0:.0f}s)")
            last = st
        if st == "completed":
            return s
        if st == "failed":
            raise SystemExit(f"任务失败 error_code={s.get('error_code')} "
                             f"{s.get('error')} {s.get('error_detail', '')}")
        time.sleep(4)
    raise SystemExit(f"超时 {timeout}s（task_id={tid}）")


def results_of(status_json: dict) -> list[str]:
    r = status_json.get("results") or []
    return [x if isinstance(x, str) else x.get("url", "") for x in r]


def emit(status_json: dict, out_dir, names, json_mode: bool, label: str):
    urls = results_of(status_json)
    saved = []
    if urls and out_dir:
        for i, u in enumerate(urls):
            nm = names[i] if names and i < len(names) else ""
            try:
                saved.append(download(u, out_dir, nm))
            except SystemExit as e:
                print(f"  ✗ 下载失败: {e}", file=sys.stderr)
    if json_mode:
        print(json.dumps({"label": label, "results": urls, "saved": saved},
                         ensure_ascii=False, indent=2))
    else:
        for s in saved:
            print(f"  ✓ {s}")
        for u in urls:
            if not saved:
                print(f"  url {u}")
    return saved


# ─────────────────────────── 子命令 ───────────────────────────
# 每个函数签名: (args, base, key, common) -> int

def cmd_health(a, base, key, c):
    code, d = http("GET", base + "/api/health", timeout=8)
    print(f"[{c['now']}] HTTP {code} {json.dumps(d, ensure_ascii=False)}")
    return 0 if code == 200 else 1


def cmd_key(a, base, key, c):
    if getattr(a, "sync", False):
        live = _read_json_key(HOME / "Library/Application Support/G-Labs Studio/webhook_config.json") \
            or _read_json_key(HOME / "Library/Application Support/G-Labs Automation/webhook_config.json")
        if not live:
            raise SystemExit("读不到 app 的 webhook_config.json，无法同步")
        kf = HOME / ".hermes/.glabs_key"
        old = _read_text(kf)
        kf.write_text(live + "\n")
        kf.chmod(0o600)
        print(f"✓ 已同步 {kf}\n  {old[:6] if old else '(空)'}… → {live[:6]}…"
              f"\n  ⚠️ drama-gateway 是启动时读一次 key —— 要重启它才生效。")
        key, c["key_src"] = live, "~/.hermes/.glabs_key（刚同步）"
    if not key:
        print("✗ 没找到 key。检查：")
    else:
        print(f"✓ key 来源: {c['key_src']}")
        print(f"  key = {key[:6]}…{key[-4:]} ({len(key)} chars)")
    print(f"  app 实时真源: {key_source_hint()}")
    if key:
        code, _ = http("GET", base + "/api/tasks", key=key, timeout=10)
        print(f"  鉴权自测: HTTP {code} {'✓ 通过' if code == 200 else '✗ 失败'}")
    return 0 if key else 1


def cmd_accounts(a, base, key, c):
    """app 当前的 Flow 账号池（只读，排查「Max Retries Exceeded」用）。"""
    rows = live_accounts()
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0 if rows else 1
    if not rows:
        print("读不到 flow_accounts.json（app 没跑过，或路径变了）")
        return 1
    print(f"{'email':<34} {'status':<8} {'tier':<6} {'credits':<8} {'img':<5} {'vid':<5} last")
    for r in rows:
        print(f"{str(r['email']):<34} {str(r['status']):<8} {str(r['tier']):<6} "
              f"{str(r['credits']):<8} {str(r['image']):<5} {str(r['video']):<5} {r['last']}")
    print("\n注：默认**不向请求里塞 account_id**，让 app 自己挑号；"
          "塞旧快照 id 会 Max Retries Exceeded。")
    return 0


# ── Workflow 节点图（离线校验；app 不提供外部触发，所以只能"写好了给 GUI 加载"）──

# 每种节点的 (输入槽模板, 输出槽模板)。None = 数量按 mode/refs 变。
WF_SOCKETS = {
    "prompt":        ([], ["Prompt"]),
    "batch_prompt":  ([], ["Prompt"]),
    "reference":     ([], ["Image"]),
    "batch_loader":  ([], ["Image"]),
    "frame_extract": (["Video"], ["Image"]),
    "render":        (["Video A", "Video B"], ["Video"]),
    "generate":      (["Prompt"], ["Image"]),                       # + Ref 1..N
    "video_generate": (["Prompt"], ["Video"]),
    "grok":          (["Prompt"], ["Output"]),
    "meta":          (["Prompt"], ["Output"]),
    "openai":        (["Prompt"], ["Image"]),
}

# 每个输入槽接受的来源类型。'string'=Prompt，'image'/'video' 对应节点输出类型。
WF_SLOT_KIND = {
    "generate":       ["string", "image"],
    "video_generate": ["string", "image"],
    "openai":         ["string", "image"],
    "grok":           ["string", "image"],
    "meta":           ["string", "image", "image", "image"],
    "frame_extract":  ["video"],
    "render":         ["video", "video"],
}


def _out_kind(node: dict) -> str:
    t = node.get("type")
    if t in ("prompt", "batch_prompt"):
        return "string"
    if t in ("generate", "openai", "frame_extract", "reference", "batch_loader"):
        return "image"
    if t in ("video_generate", "render"):
        return "video"
    return "any"                       # grok / meta 输出 any


def check_workflow(doc: dict) -> tuple[list, list]:
    errs, warns = [], []
    nodes = doc.get("nodes")
    edges = doc.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return ["nodes 缺失或为空"], warns
    if not isinstance(edges, list):
        return ["edges 缺失"], warns

    id2idx = {}
    for i, n in enumerate(nodes):
        for f in ("id", "type", "x", "y", "inputs", "outputs", "values"):
            if f not in n:
                errs.append(f"节点[{i}] 缺字段 `{f}`")
        t = n.get("type")
        if t not in WF_SOCKETS:
            errs.append(f"节点[{i}] 未知 type `{t}`（合法：{', '.join(WF_SOCKETS)}）")
            continue
        if not isinstance(n.get("inputs"), list) or not isinstance(n.get("outputs"), list):
            errs.append(f"节点[{i}] inputs/outputs 必须是数组（边按**索引**引用它们）")
        if n["id"] in id2idx:
            errs.append(f"节点[{i}] id={n['id']} 重复")
        id2idx[n["id"]] = i
        if t == "reference" and n.get("ref_mode") != "pro":
            warns.append(f"节点[{i}] reference 一般要带 \"ref_mode\": \"pro\"")

    prompt_ins = {}
    for k, e in enumerate(edges):
        for f in ("start_node", "start_socket", "end_node", "end_socket"):
            if f not in e:
                errs.append(f"边[{k}] 缺字段 `{f}`")
        s, ss, d, ds = (e.get("start_node"), e.get("start_socket"),
                        e.get("end_node"), e.get("end_socket"))
        if not all(isinstance(v, int) for v in (s, ss, d, ds)):
            errs.append(f"边[{k}] 四个字段都必须是**整数索引**")
            continue
        for label, idx in (("start_node", s), ("end_node", d)):
            if not 0 <= idx < len(nodes):
                errs.append(f"边[{k}] {label}={idx} 越界（节点只有 {len(nodes)} 个，0..{len(nodes)-1}）")
        if s == d:
            errs.append(f"边[{k}] 自环")
        if s >= len(nodes) or d >= len(nodes):
            continue
        if ss >= len(nodes[s]["outputs"]):
            errs.append(f"边[{k}] start_socket={ss} 越界（节点[{s}] 只有 {len(nodes[s]['outputs'])} 个输出）")
        if ds >= len(nodes[d]["inputs"]):
            errs.append(f"边[{k}] end_socket={ds} 越界（节点[{d}] 只有 {len(nodes[d]['inputs'])} 个输入）")
        if ds == 0:
            prompt_ins[d] = prompt_ins.get(d, 0) + 1
        if s < len(nodes) and d < len(nodes) and ss < len(nodes[s]["outputs"]) \
                and ds < len(nodes[d]["inputs"]):
            need = WF_SLOT_KIND.get(nodes[d]["type"], [])
            if ds < len(need):
                have = _out_kind(nodes[s])
                if need[ds] != have and have != "any" and need[ds] != "string":
                    errs.append(f"边[{k}] 类型不匹配：{nodes[s]['type']}({have}) → "
                                f"{nodes[d]['type']} 第 {ds} 槽(要 {need[ds]})")
    for idx, cnt in prompt_ins.items():
        if cnt > 1:
            errs.append(f"节点[{idx}] 的 Prompt 槽（索引 0）被连了 {cnt} 条边 —— 最多 1 条")

    # 环检测（拓扑执行不了有环的图）
    adj = {}
    for e in edges:
        s, d = e.get("start_node"), e.get("end_node")
        if isinstance(s, int) and isinstance(d, int) and 0 <= s < len(nodes) and 0 <= d < len(nodes):
            adj.setdefault(s, []).append(d)
    WHITE, GREY, BLACK = 0, 1, 2
    color = [WHITE] * len(nodes)

    def dfs(u):
        color[u] = GREY
        for v in adj.get(u, []):
            if color[v] == GREY:
                errs.append(f"检测到环：节点[{u}] → 节点[{v}]（RUN FLOW 会中止）")
                return
            if color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    for i in range(len(nodes)):
        if color[i] == WHITE:
            dfs(i)
    return errs, warns


def cmd_workflow(a, base, key, c):
    """校验一个 Workflow JSON（纯离线，不碰网络、不花额度）。"""
    p = pathlib.Path(a.file).expanduser()
    if not p.exists():
        raise SystemExit(f"找不到 {p}")
    doc = json.loads(p.read_text())
    errs, warns = check_workflow(doc)
    n, e = len(doc.get("nodes", [])), len(doc.get("edges", []))
    if a.json:
        print(json.dumps({"file": str(p), "nodes": n, "edges": e,
                          "errors": errs, "warnings": warns}, ensure_ascii=False, indent=2))
        return 1 if errs else 0
    print(f"{p}\n  节点 {n} 个 · 边 {e} 条")
    for w in warns:
        print(f"  ⚠️  {w}")
    for x in errs:
        print(f"  ✗  {x}")
    if not errs:
        print("  ✅ 结构合法（边索引/槽位/类型/无环都通过）")
        print("  注：下拉框的**取值文本**校验不了（要 app 的语言包），首次加载请核对。")
    return 1 if errs else 0


def cmd_tasks(a, base, key, c):
    code, d = http("GET", base + "/api/tasks", key=key, timeout=15)
    tasks = (d or {}).get("tasks", [])[: a.limit]
    if a.json:
        print(json.dumps(tasks, ensure_ascii=False, indent=2))
        return 0
    print(f"{'task_id':<10} {'type':<7} {'status':<10} {'created':<20} prompt")
    for t in tasks:
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime(t.get("created_at", 0)))
        print(f"{t.get('task_id',''):<10} {t.get('type',''):<7} {t.get('status',''):<10} "
              f"{ts:<20} {(t.get('prompt') or '')[:50]}")
    return 0


def cmd_status(a, base, key, c):
    code, d = http("GET", f"{base}/api/status/{a.task_id}", key=key, timeout=15)
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0 if code == 200 else 1


def cmd_image(a, base, key, c):
    payload = {"prompt": a.prompt, "model": a.model, "aspect_ratio": a.ratio}
    payload.update(build_refs(a.ref, a.ref_mode))
    if a.upscale:
        payload["upscale"] = a.upscale if isinstance(a.upscale, list) else [a.upscale]
    if c["account"]:
        payload["account_id"] = c["account"]
    tid = submit(base, key, "/api/image/generate", payload, a.dry_run)
    if a.no_wait:
        return 0
    emit(wait(base, key, tid, a.timeout), a.out, a.name, a.json, "image")
    return 0


def cmd_video(a, base, key, c):
    payload = {
        "prompt": a.prompt,
        "model": a.model,
        "aspect_ratio": a.ratio,
        "mode": a.mode,
        "resolution": [a.resolution],
        "video_length": a.length,
    }
    payload.update(build_refs(a.ref, a.ref_mode))
    if a.ref_video:
        payload.update(build_refs(a.ref_video, a.ref_mode, field="reference_videos"))
    if a.voice:
        payload["voice"] = a.voice
    if c["account"]:
        payload["account_id"] = c["account"]
    tid = submit(base, key, "/api/video/generate", payload, a.dry_run)
    if a.no_wait:
        return 0
    emit(wait(base, key, tid, a.timeout), a.out, a.name, a.json, "video")
    return 0


def cmd_grok(a, base, key, c):
    payload = {"prompt": a.prompt, "mode": a.mode, "aspect_ratio": a.ratio}
    if a.mode.startswith(("i2i", "i2v")):
        payload.update(build_refs(a.ref, a.ref_mode))
        if a.mode == "i2v":
            payload["first_frame"] = a.first_frame
    if a.mode.endswith("v"):
        payload["video_length"] = a.length
        payload["resolution"] = a.resolution
    tid = submit(base, key, "/api/grok/generate", payload, a.dry_run)
    if a.no_wait:
        return 0
    emit(wait(base, key, tid, a.timeout), a.out, a.name, a.json, "grok")
    return 0


def cmd_meta(a, base, key, c):
    # ⚠️ meta 用**命名字段**，不是 reference_images 列表
    payload = {"prompt": a.prompt, "mode": a.mode, "aspect_ratio": a.ratio, "count": a.count}
    for field, key_attr in (("character_image", "character_img"), ("scene_image", "scene_img"),
                            ("style_image", "style_img"), ("start_image", "start_img"),
                            ("end_image", "end_img")):
        v = getattr(a, key_attr, None)
        if v:
            payload[field] = v if v.startswith("data:") else to_data_url(v)
    if a.mode.endswith("v"):
        payload["resolution"] = a.resolution
    tid = submit(base, key, "/api/meta/generate", payload, a.dry_run)
    if a.no_wait:
        return 0
    emit(wait(base, key, tid, a.timeout), a.out, a.name, a.json, "meta")
    return 0


def cmd_openai(a, base, key, c):
    payload = {"prompt": a.prompt, "aspect_ratio": a.ratio, "quality": a.quality,
               "prompt_mode": a.prompt_mode, "reasoning": a.reasoning,
               "web_search": a.web_search}
    payload.update(build_refs(a.ref, a.ref_mode))
    tid = submit(base, key, "/api/openai/generate", payload, a.dry_run)
    if a.no_wait:
        return 0
    emit(wait(base, key, tid, a.timeout), a.out, a.name, a.json, "openai")
    return 0


def cmd_upscale(a, base, key, c):
    """本地 Real-ESRGAN —— **不耗 G-Labs quota，也不限 MAX**。当链路体检用。"""
    payload = {"scale": a.scale, "format": a.format, "suffix": a.suffix, "tta": a.tta}
    if a.image_path:
        payload["image_path"] = str(pathlib.Path(a.image_path).expanduser())
    elif a.image:
        payload["image"] = a.image if a.image.startswith("data:") else to_data_url(a.image)
        if a.filename:
            payload["filename"] = a.filename
    else:
        raise SystemExit("要 --image <本地图片> 或 --image-path <同机绝对路径>")
    if a.model:
        payload["model"] = a.model
    tid = submit(base, key, "/api/upscale/generate", payload, a.dry_run)
    if a.no_wait:
        return 0
    emit(wait(base, key, tid, a.timeout), a.out, a.name, a.json, "upscale")
    return 0


# ─────────────────────────── CLI ───────────────────────────

def add_common(sp):
    sp.add_argument("--base", default=DEFAULT_BASE, help=f"G-Labs 地址（默认 {DEFAULT_BASE}）")
    sp.add_argument("--key", default="", help="显式 key（默认自动解析）")
    sp.add_argument("--account-id", default="", help=(
        "钉死用哪个账号（默认不传，让 app 自己轮换）。"
        "传 `legacy` 会用 providers.ini 里那个**旧快照** id —— 会 Max Retries Exceeded，别用"))
    sp.add_argument("--dry-run", action="store_true", help="只打印请求体，不提交、零消耗")
    sp.add_argument("--no-wait", action="store_true", help="入队就返回，不轮询")
    sp.add_argument("--timeout", type=int, default=1800, help="轮询超时秒（默认 1800）")
    sp.add_argument("--out", default="./glabs-out", help="产物目录（默认 ./glabs-out）")
    sp.add_argument("--name", nargs="*", default=None, help="产物文件名（可多个）")
    sp.add_argument("--json", action="store_true", help="机器可读输出")
    sp.add_argument("--ref", nargs="*", default=[], help="参考图（本地路径，可多个）")
    sp.add_argument("--ref-mode", choices=["base64", "path"], default="base64",
                    help="参考图传递方式（base64 默认，可绕开 TCC 限制）")


def build_parser():
    p = argparse.ArgumentParser(prog="glabs.py", description="G-Labs Studio 原生 Webhook API 客户端")
    sub = p.add_subparsers(dest="cmd", required=True)

    def mk(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        add_common(s)
        s.set_defaults(fn=fn)
        return s

    mk("health", cmd_health, "服务健康（免 key）")
    s = mk("key", cmd_key, "显示 key 来源 + 鉴权自测")
    s.add_argument("--sync", action="store_true",
                   help="把 app 里的实时 key 同步进 ~/.hermes/.glabs_key（app 改名/重置后跑这个）")
    mk("status", cmd_status, "查单个任务").add_argument("task_id")

    s = mk("tasks", cmd_tasks, "最近任务列表")
    s.add_argument("--limit", type=int, default=20)

    mk("accounts", cmd_accounts, "app 的 Flow 账号池（credits / 状态，排查失败用）")

    s = mk("workflow", cmd_workflow, "离线校验一个 Workflow JSON（不花额度）")
    s.add_argument("file")

    s = mk("image", cmd_image, "出图（Nano Banana 系列）")
    s.add_argument("--prompt", required=True)
    s.add_argument("--model", default="nano_banana_pro",
                   choices=["nano_banana_2", "nano_banana_pro", "nano_banana_2_lite"])
    s.add_argument("--ratio", default="16:9", choices=["1:1", "3:4", "4:3", "9:16", "16:9"])
    s.add_argument("--upscale", nargs="*", default=[], choices=["2K", "4K"])

    s = mk("video", cmd_video, "出片（Veo 3.1 / Omni Flash）")
    s.add_argument("--prompt", required=True)
    s.add_argument("--model", default="omni_flash",
                   choices=["omni_flash", "veo_31_fast", "veo_31_lite", "veo_31_quality",
                            "veo_31_lite_relaxed"])
    s.add_argument("--ratio", default="16:9", choices=["16:9", "9:16"])
    s.add_argument("--mode", default="components",
                   choices=["text_to_video", "start_image", "start_end_image", "components"])
    s.add_argument("--resolution", default="720p", choices=["360p", "720p", "1080p", "4K"])
    s.add_argument("--length", type=int, default=6, choices=[4, 6, 8, 10])
    s.add_argument("--ref-video", nargs="*", default=[], help="参考视频（Omni components，≤10s）")
    s.add_argument("--voice", default="")

    s = mk("grok", cmd_grok, "Grok Imagine（走 grok.com 登录态 + Auth Helper 扩展）")
    s.add_argument("--prompt", required=True)
    s.add_argument("--mode", default="t2i", choices=["t2i", "i2i", "t2v", "i2v"])
    s.add_argument("--ratio", default="9:16")
    s.add_argument("--length", type=int, default=6, choices=[6, 10, 15])
    s.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    s.add_argument("--first-frame", action="store_true")

    s = mk("meta", cmd_meta, "Meta AI / vibes.ai")
    s.add_argument("--prompt", required=True)
    s.add_argument("--mode", default="t2i", choices=["t2i", "t2v", "i2i", "i2v"])
    s.add_argument("--ratio", default="9:16", choices=["9:16", "16:9", "1:1"])
    s.add_argument("--resolution", default="720p", choices=["480p", "720p"])
    s.add_argument("--count", type=int, default=1, choices=[1, 2, 3, 4])
    s.add_argument("--character-img", default="")
    s.add_argument("--scene-img", default="")
    s.add_argument("--style-img", default="")
    s.add_argument("--start-img", default="")
    s.add_argument("--end-img", default="")

    s = mk("openai", cmd_openai, "GPT Image 2")
    s.add_argument("--prompt", required=True)
    s.add_argument("--ratio", default="1:1")
    s.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    s.add_argument("--prompt-mode", default="auto", choices=["auto", "direct"])
    s.add_argument("--reasoning", default="none",
                   choices=["none", "low", "medium", "high", "xhigh", "max"])
    s.add_argument("--web-search", action="store_true")

    s = mk("upscale", cmd_upscale, "本地放大（Real-ESRGAN，不耗 quota）")
    s.add_argument("--image", default="", help="本地图片路径（转 base64，跨机可用）")
    s.add_argument("--image-path", default="", help="同机绝对路径（大图首选，免 base64 膨胀）")
    s.add_argument("--filename", default="")
    s.add_argument("--model", default="")
    s.add_argument("--scale", type=int, default=4, choices=[2, 3, 4, 6, 8])
    s.add_argument("--format", default="auto", choices=["auto", "png", "jpg", "webp"])
    s.add_argument("--suffix", default="_upscaled")
    s.add_argument("--tta", action="store_true")

    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    base = a.base.rstrip("/")
    key, src = resolve_key(a.key)
    a.out = pathlib.Path(a.out).expanduser()
    # 账号：默认 **不传**（app 自己轮换）。`legacy` 才用 providers.ini 里的旧快照 id。
    acct = ""
    if getattr(a, "account_id", ""):
        acct = provider_account_id() if a.account_id == "legacy" else a.account_id
    c = {"key_src": src, "account": acct,
         "now": time.strftime("%Y-%m-%d %H:%M:%S")}

    # 只读命令不因缺 key 而中断（health 本来就不要 key）
    if not key and a.cmd not in ("health",):
        print(f"✗ 没找到 G-Labs API key。app 实时真源: {key_source_hint()}", file=sys.stderr)
        print("  把 webhook_config.json 里的 api_key 写进 ~/.hermes/.glabs_key 即可。", file=sys.stderr)
        return 1
    if not key and a.cmd == "health":
        pass
    return a.fn(a, base, key, c)


if __name__ == "__main__":
    sys.exit(main())
