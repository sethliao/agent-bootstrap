#!/usr/bin/env python3
# drama-panel.py — DramaClaw 预检控制台（主 GUI 之前用），:8899
# 状态检查 / 一键启动 / TTS 声线切换 / TTS 试听。纯 stdlib，无第三方依赖。
import base64
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.path.expanduser("~")
INI = os.path.join(HOME, ".hermes/drama-gateway/providers.ini")
GW_URL = "http://127.0.0.1:8790"
GW_SCRIPT = os.path.join(HOME, "Code/drama-claw-hermes/agy-shim/drama_gateway.py")
START_SCRIPT = os.path.join(HOME, "Code/drama-claw-hermes/bin/start-dramaclaw.sh")
LOG_DIR = os.path.join(HOME, "Code/drama-claw-hermes/logs")
PORT = 8899

SERVICES = [
    ("DramaClaw API", 8780, "后端 API"),
    ("drama-gateway", 8790, "LLM/图像/视频/TTS 网关"),
    ("XiaHua GUI", 8080, "主界面"),
    ("G-Labs Automation", 8765, "图像/视频生成（桌面 App）"),
    ("Voice Studio", 8766, "TTS App（已弃用，可不管）"),
]

VOICES = [
    ("en-US-GuyNeural", "Guy · 阳光少年（英文默认）", "男"),
    ("en-US-ChristopherNeural", "Christopher · 温暖沉稳", "男"),
    ("en-US-AndrewNeural", "Andrew · 平静友好", "男"),
    ("en-US-EricNeural", "Eric · 活力", "男"),
    ("en-US-AndrewMultilingualNeural", "Andrew 多语言 · 中英混读", "男"),
    ("en-GB-RyanNeural", "Ryan · 英音", "男"),
    ("en-NZ-MitchellNeural", "Mitchell · 纽村口音", "男"),
    ("zh-CN-YunjianNeural", "云健 Yunjian · 温暖少年（中文）", "男"),
    ("zh-CN-YunxiNeural", "云希 Yunxi · 活泼（中文）", "男"),
    ("zh-CN-YunxiaNeural", "云夏 Yunxia · 少年（中文）", "男"),
    ("zh-CN-YunyangNeural", "云扬 Yunyang · 沉稳/新闻（中文）", "男"),
    ("en-US-JennyNeural", "Jenny · 英文女声", "女"),
    ("zh-CN-XiaoxiaoNeural", "晓晓 Xiaoxiao · 中文女声", "女"),
    ("zh-CN-XiaoyiNeural", "晓伊 Xiaoyi · 中文女声", "女"),
]
PROVIDERS = [("edge_tts", "Edge TTS（免费）"), ("volc_tts", "火山 doubao-seed（需 ARK key）")]


def port_up(p):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", p)) == 0
    finally:
        s.close()


def read_audio_cfg():
    prov, voice = "edge_tts", "zh-CN-YunjianNeural"
    try:
        lines = open(INI, encoding="utf-8").read().splitlines()
        in_audio = False
        for ln in lines:
            t = ln.strip()
            if t.startswith("[") :
                in_audio = (t == "[audio]")
                continue
            if in_audio and "=" in t:
                k, v = [x.strip() for x in t.split("=", 1)]
                if k == "provider":
                    prov = v
                elif k == "voice":
                    voice = v
    except Exception:
        pass
    return prov, voice


def write_audio_cfg(prov, voice):
    lines = open(INI, encoding="utf-8").read().splitlines()
    out, in_audio, wrote = [], False, False
    for ln in lines:
        t = ln.strip()
        if t.startswith("["):
            in_audio = (t == "[audio]")
            out.append(ln)
            if in_audio and not wrote:
                out.append("provider = %s" % prov)
                out.append("voice = %s" % voice)
                wrote = True
            continue
        if in_audio and "=" in t and t.split("=", 1)[0].strip() in ("provider", "voice"):
            continue
        out.append(ln)
    if not wrote:
        out.append("")
        out.append("[audio]")
        out.append("provider = %s" % prov)
        out.append("voice = %s" % voice)
    open(INI, "w", encoding="utf-8").write("\n".join(out) + "\n")


def restart_gateway():
    try:
        r = subprocess.run(["lsof", "-nP", "-iTCP:8790", "-sTCP:LISTEN", "-t"],
                           capture_output=True, text=True, timeout=5)
        for pid in r.stdout.split():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    except Exception:
        pass
    time.sleep(1)
    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(os.path.join(LOG_DIR, "gateway.log"), "ab")
    subprocess.Popen(["nohup", "/usr/bin/python3", GW_SCRIPT, "--port", "8790"],
                     stdout=log, stderr=log, start_new_session=True)
    for _ in range(25):
        if port_up(8790):
            break
        time.sleep(1)
    return port_up(8790)


def start_stack():
    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(os.path.join(LOG_DIR, "start.log"), "ab")
    subprocess.Popen(["bash", START_SCRIPT], stdout=log, stderr=log, start_new_session=True)


def test_tts(text, voice):
    body = json.dumps({"input": text, "voice": voice}).encode()
    req = urllib.request.Request(GW_URL + "/v1/audio/speech", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "audio/mpeg")


PAGE = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DramaClaw 控制台</title>
<style>
:root{--bg:#111318;--card:#1a1e26;--line:#2a3040;--fg:#e8ecf4;--mut:#8b94a7;--ok:#3ddc84;--bad:#ff5c5c;--acc:#5b8cff}
*{box-sizing:border-box;font-family:-apple-system,"PingFang SC",sans-serif}
body{margin:0;background:var(--bg);color:var(--fg);padding:24px;max-width:920px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
.card h2{font-size:15px;margin:0 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.svc{display:flex;align-items:center;gap:10px;background:#141821;border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.dot{width:10px;height:10px;border-radius:50%;flex:none}
.dot.up{background:var(--ok)}.dot.down{background:var(--bad)}
.svc .n{font-weight:600}.svc .p{color:var(--mut);font-size:12px}
label{font-size:12px;color:var(--mut);display:block;margin:8px 0 4px}
select,textarea,input[type=text]{width:100%;background:#141821;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
button{background:var(--acc);color:#fff;border:none;border-radius:8px;padding:9px 16px;font-size:14px;cursor:pointer;margin:8px 6px 0 0}
button.sec{background:#2a3040}
#ttsResult{margin-top:12px}
audio{width:100%;margin-top:8px}
.badge{font-size:11px;padding:2px 8px;border-radius:20px;margin-left:6px}
.badge.m{background:#22314f;color:#8fb0ff}.badge.f{background:#3f2430;color:#ff9db1}
#status{color:var(--mut);font-size:12px}
</style></head><body>
<h1>🎬 DramaClaw 控制台</h1>
<div class="sub">主 GUI 之前的预检面板 · 一键启动 / TTS 声线切换 / 试听 &nbsp;·&nbsp; <span id="status">载入中…</span></div>

<div class="card"><h2>服务状态</h2><div class="grid" id="services"></div>
<div style="margin-top:12px">
<button onclick="startStack()">🚀 启动整个栈</button>
<a href="http://127.0.0.1:8080" target="_blank"><button class="sec">打开主 GUI →</button></a>
</div></div>

<div class="card"><h2>TTS 声线（保存后自动重启网关）</h2>
<label>后端 provider</label>
<select id="provider"></select>
<label>声线 voice（<span style="color:#8fb0ff">男声优先</span>）</label>
<select id="voice"></select>
<button onclick="saveTts()">💾 保存并重启</button>
<button class="sec" onclick="refresh()">↻ 刷新状态</button>
</div>

<div class="card"><h2>快速试听（走真实网关管道）</h2>
<input type="text" id="ttsText" value="你好，我是莫莫，一只住在唐人街的小熊猫。">
<button onclick="runTest()">▶ 试听</button>
<div id="ttsResult"></div>
</div>

<script>
async function j(u,o){const r=await fetch(u,o);return r.json()}
async function refresh(){const s=await j('/api/status');
 document.getElementById('status').textContent='更新于 '+new Date().toLocaleTimeString();
 const g=document.getElementById('services');g.innerHTML='';
 for(const sv of s.services){const up=sv.up;
  g.insertAdjacentHTML('beforeend',
   `<div class="svc"><span class="dot ${up?'up':'down'}"></span><div><div class="n">${sv.name}</div><div class="p">:${sv.port} · ${sv.desc} · ${up?'运行中':'未运行'}</div></div></div>`);}
 const pSel=document.getElementById('provider'),vSel=document.getElementById('voice');
 if(pSel.options.length===0){for(const [v,l] of s.providers)pSel.add(new Option(l,v));}
 if(vSel.options.length===0){for(const [v,l,g] of s.voices)vSel.add(new Option((g==='男'?'♂ ':'♀ ')+l,v));}
 pSel.value=s.tts.provider;vSel.value=s.tts.voice;
}
async function saveTts(){await j('/api/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:document.getElementById('provider').value,voice:document.getElementById('voice').value})});
 alert('已保存并重启网关');refresh();}
async function startStack(){await j('/api/start',{method:'POST'});alert('启动脚本已在后台运行（约 30s 就绪），稍后刷新本页看状态');setTimeout(refresh,3000);}
async function runTest(){const r=await j('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:document.getElementById('ttsText').value,voice:document.getElementById('voice').value})});
 document.getElementById('ttsResult').innerHTML=`<audio controls src="data:${r.mime};base64,${r.data}"></audio><div style="color:var(--mut);font-size:12px;margin-top:4px">${r.duration}s · ${r.bytes}B</div>`;}
refresh();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/status":
            prov, voice = read_audio_cfg()
            payload = {
                "services": [{"name": n, "port": p, "desc": d, "up": port_up(p)} for n, p, d in SERVICES],
                "providers": PROVIDERS, "voices": VOICES,
                "tts": {"provider": prov, "voice": voice},
            }
            return self._send(200, json.dumps(payload, ensure_ascii=False).encode())
        return self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception:
            body = {}
        p = self.path.split("?")[0]
        if p == "/api/tts":
            write_audio_cfg(str(body.get("provider") or "edge_tts"),
                            str(body.get("voice") or "zh-CN-YunjianNeural"))
            ok = restart_gateway()
            return self._send(200, json.dumps({"ok": ok}).encode())
        if p == "/api/test":
            try:
                data, mime = test_tts(str(body.get("text") or "你好。"),
                                      str(body.get("voice") or "zh-CN-YunjianNeural"))
                return self._send(200, json.dumps({
                    "mime": mime, "bytes": len(data),
                    "duration": round(len(data) / 4800, 1),
                    "data": base64.b64encode(data).decode()}, ensure_ascii=False).encode())
            except Exception as e:
                return self._send(502, json.dumps({"error": str(e)}, ensure_ascii=False).encode())
        if p == "/api/start":
            start_stack()
            return self._send(200, json.dumps({"ok": True}).encode())
        return self._send(404, json.dumps({"error": "not found"}).encode())


if __name__ == "__main__":
    print(f"DramaClaw 控制台: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
