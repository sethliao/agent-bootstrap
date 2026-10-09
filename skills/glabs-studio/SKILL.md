---
name: glabs-studio
description: 直连 G-Labs Studio 本地 Webhook API 出图/出片/放大（6 个端点，含免费的本地 Real-ESRGAN 放大）。当需要"出一张图/一条视频"、"批量出图"、"放大某张图"、"链路体检"、"G-Labs key 失效了"、"gateway 挂了"时使用。也覆盖 app 改名/换 key 的排查。
tags:
  - glabs
  - image-generation
  - video-generation
  - local-api
  - upscale
agent_created: true
---

# G-Labs Studio 本地生成 API

Seth 的**底层生图/生视频平台**。桌面 app「**G-Labs Studio**」（2026-09-19 由 *G-Labs Automation* 改名），
本机 Webhook 服务 `127.0.0.1:8765`，一个 key 通吃 Google Flow（Nano Banana / Veo / Omni Flash）、
Grok Imagine、Meta AI、GPT Image 2，外加**本地**放大。

> 改名提示：库内旧笔记写「G-Labs Automation」＝同一个东西。名字变了，端口没变，**key 会重置**。

## 什么时候用这个 skill / 什么时候用 drama-gateway

| 场景 | 用谁 | 为什么 |
|---|---|---|
| 只想出图 / 出片（复刻、试片、素材） | **本 skill 直连 :8765** | 少一跳，报错是原生的，还能用 upscale |
| 放大图片 | **本 skill** | gateway 没接 upscale；**本地 GPU，不耗 quota** |
| Grok / Meta / GPT Image 2 | **本 skill** | gateway 只做了 image+video |
| DramaClaw 全流程（剧本→分镜→合成） | `drama-claw-hermes` skill + gateway :8790 | DramaClaw 只认 OpenAI 兼容协议 |
| 需要 TTS | `drama-claw-hermes`（gateway :8790） | 语音没进 Webhook API |

## 快速开始

```bash
G=~/.workbuddy/skills/glabs-studio/scripts/glabs.py
P=~/.workbuddy/binaries/python/versions/3.13.12/bin/python3

$P $G health                      # 服务活着吗（免 key）
$P $G key                         # key 从哪来的 + 鉴权自测 ← 出问题先跑这个
$P $G accounts                    # Flow 账号池：credits / 是否过期 ← 第二个该跑的
$P $G tasks --limit 10            # 最近任务（含失败原因）

# 出图（参考图默认走 base64）
$P $G image --prompt "…" --model nano_banana_pro --ratio 16:9 --out ./frames --name s1.png

# 出片（不锁首帧，走 components）
$P $G video --prompt "…" --model omni_flash --length 6 --resolution 720p --ref key.jpg --out ./clips

# 出片（锁首帧 / 首尾帧 —— 2026-09-21 A/B 实测过）
$P $G video --prompt "…" --model omni_flash --length 4 --mode start_image     --ref first.jpg  --out ./clips
$P $G video --prompt "…" --model omni_flash --length 6 --mode start_end_image --ref first.jpg --ref last.jpg --out ./clips

# 放大（不耗 quota —— 拿它当免费体检）
$P $G upscale --image ./x.png --scale 4 --out ./up
```

**所有生成类命令都支持 `--dry-run`：只打印请求体、不提交、零消耗。**
烧 quota 前先 `--dry-run` 给 Seth 过目 —— 这是他定的铁律。

### ⭐ `--mode` 的语义（2026-09-21 实测，别再猜）

**它是「软锚定」不是「硬锁帧」。** 同 prompt 同首帧跑 A/B，第 0 帧 vs 参考：

| mode | 参考图语义 | 实测 PSNR | 用在哪 |
|---|---|---|---|
| `components`（默认） | 全部 ref = 素材，**构图自由重排** | 12.88 dB | 常规出片（Seth 默认规矩） |
| `start_image` | 第 1 张 = 首帧锚点 | **19.28 dB**（+6.4） | 要「从这张图起步」的叙事 |
| `start_end_image` | 第 1 张 = 首帧，第 2 张 = 尾帧 | 首 19.16 / 尾 20.18 | **链式延续 / 首尾帧转场** |
| `text_to_video` | 不用参考图 | — | 纯文生视频 |

- 同图 ≈ ∞，**>30 dB 才算「像同一张」** → 19 dB 是「构图主体都在，细节自由发挥」。
  既不会被僵硬锁帧卡住，**也别指望帧级无缝**（跨段接头用 0.2–0.3s 叠化掩掉）。
- ⚠️ **锁首帧保的是「构图」，不保证「细节丰富度」** —— 同首帧下 `components` 保住了工作灯/道具/霓虹，
  `start_image` 反而掉了一部分（要把画面让给被锁定的构图）。
- ⚠️ **只在直连 :8765 时生效**；走 drama-gateway 时它按「有没有 reference_images」自己判，`mode` 传不进去。
- ⚠️ **验证首尾帧要抽 `t=0` 和 `t=end`**，别用等距采样代替 —— 等距采样会把「已过渡的中段」当首帧，误判成「没锁住」。

## 端点速查（原生 `/api/*`）

> ✅ 下面这份字段清单**抄自 app 内嵌的官方文档**（`strings -a "/Applications/G-Labs Studio.app/Contents/MacOS/G-LabsStudio"`
> 里有一段完整 API 说明），不是猜的。app 二进制里还有多语言说明书 HTML，排障时值得先翻它。

| 方法 | 路径 | 需 key | 说明 |
|---|---|:--:|---|
| GET | `/api/health` | ❌ | `{status, server, uptime, tasks_pending, tasks_running}` |
| POST | `/api/image/generate` | ✅ | **只有 5 个字段**：`prompt`(必) · `model` ∈ nano_banana_2 / _pro / _2_lite · `aspect_ratio` ∈ 1:1/3:4/4:3/9:16/16:9 · `reference_images`≤10（base64 数组）· `upscale` ∈ [2K,4K]（4K 需 ULTRA） |
| POST | `/api/video/generate` | ✅ | `model` ∈ omni_flash / veo_31_fast/​lite/​quality / veo_31_lite_relaxed；`mode` ∈ text_to_video(默认,0 refs)/​start_image(1 ref)/​start_end_image(2 refs 首+尾)/​components(Veo≤3 / **Omni Flash≤7**, 支持 voice)；`resolution` **是数组**；`video_length` Veo 4/6/8、Omni 4/6/8/10；`reference_video` 仅 Omni+components（≤10s 改片，可配 ≤5 张配料图） |
| POST | `/api/grok/generate` | ✅ | `mode` ∈ t2i/i2i/t2v/i2v；`first_frame`(i2v,true=当开头帧/​false=配料)；video_length 6/10/15；480p/720p/1080p |
| POST | `/api/meta/generate` | ✅ | ⭐ **命名字段（按语义分槽）**：`character_image`/`scene_image`/`style_image`/`start_image`/`end_image`；`count` 1–4 |
| POST | `/api/openai/generate` | ✅ | GPT Image 2；`quality`/`prompt_mode`(auto\|direct)/`reasoning`/`web_search`；ref≤5（**positional，不支持 @tag**） |
| POST | `/api/upscale/generate` | ✅ | **本地 Real-ESRGAN，无 quota**；`image_path`(同机) 或 `image`(base64)；scale 2–8；`model`/`format`/`tile`/`tta` |
| GET | `/api/status/{id}` | ✅ | `pending`→`running`→`completed`/`failed` |
| GET | `/api/result/{id}` | ✅ | 完成后取结果 |
| GET | `/api/files/{name}` | ❌ | 直接下载产物 |
| GET | `/api/tasks` | ✅ | 最近 50 条（**字段只有** `task_id/type/status/prompt/created_at`，**不记参考图**） |

### ⭐⭐ 参考图话语权 = 1 ÷ prompt 指令密度（2026-09-21 实测定论）

**`/api/image/generate` 里没有任何「ref 强度 / ref 模式 / 角色锁」的字段** ——
参考图只是一个无序的 base64 数组，语义全靠模型自己仲裁。
→ **prompt 写得越自足，参考图越退化成「风格参考」。**

| 场景 | prompt 长度 | 参考图生效程度 |
|---|---|---|
| C1 / C3 / X 配方的场景镜头 | **688–1766 字** | ✅ 身份锁死（人物逐特征零丢失、六帧零漂移） |
| 一张 4000+ 字的「角色设定表排版」prompt | **3947–4914 字** | 🟡 只拿到服装 / 色板 / 材质，结构比例全按文字走 |

- ⚠️ **长 prompt 还会让模型偏科**：v2 里我堆了一串头发禁令 → 头发修对了，
  但头身比 / 腮 / 鼻 / 唇全被牺牲。**禁令越多，被牺牲的旁支越多。**
- ✅ **要锁角色就不要让 prompt 自己把话说全**：短 prompt（≤300 字）+ 参考图。
- ✅ **要排版（设定表 / 海报 / 看板）就别指望 AI**：AI 出「单视角角色图」，排版自己合成
  （还能顺带遵守库根 `DESIGN.md`，AI 排版图永远对不上 GrainyHue 的字体与色板）。
- ⛔ **别去 API 里找 `ref_mode`**：GUI 有（`manual`/`all`/`sequential`/`Default`，部分档位要 Plus/Max，
  见 `~/Library/Application Support/G-Labs Studio/settings.json` → `.image.ref_mode`），
  但**只在 GUI 的 ImageCreatorPage / VibesPage / grok 页生效**；webhook 有自己独立的一套
  （`_ref_source` / `_video_ref_source` / `_cleanup_temp_refs`），`ref_mode` 传不进去。
- ✅ **唯一「具名分槽」的端点是 `/api/meta/generate`**（`character_image` / `style_image` …），
  理论上比无序数组强得多的身份锚，但它是 Meta AI、画质低一档 —— 要用得先实测画质代价。

### ⭐ 怎么核实参考图真的送进去了（下次不用再猜）

```bash
grep -n "parsed (" ~/Library/Application\ Support/G-Labs\ Studio/logs/app_*.log | tail
#   📦 Task <id> parsed (N refs)          ← 载荷解析到几张
#   📤 UPLOAD START: N reference image(s) ← 真去上传了
#   ✅ [1/N] Upload OK (16.8s): wh_ref_xxx.png
#   📊 UPLOAD COMPLETE: Cache hits / New uploads / Total time
```
- `Cache hits: 0 / New uploads: N` → **N 张都是真上传**（不是命中缓存空跑）。
- 上传耗时占整轮很大一块：**2 张 ≈ 26s**（出图 60s 里的一半），出图耗时 ≈ 上传 + 生成。
- ⚠️ `wh_ref_*.png` 临时文件**任务结束就被 `_cleanup_temp_refs` 清掉**，
  想抓现行得在任务进行中去看 `~/Library/Application Support/G-Labs Studio/temp/`。

- 认证头：**`X-API-Key`**。
- 提交返回 **202** + `task_id`（8 位十六进制）。轮询间隔 4s，`status==completed` 后从 `results[]` 取 URL 下载。
- 失败看 `error_code`：`429` = 配额满。upscale 专属：`503 ENGINE_MISSING` / `503 NO_VULKAN_DEVICE` / `507 GPU_OUT_OF_MEMORY`。
- **任务在内存里**：app 一重启，`task_id` 和结果就没了 → 提交后同会话内轮询+下载。
- Webhook 服务器需要 **MAX 计划**（否则 403）；这是 app 侧的事，不是 key 的问题。

## 铁律（都是踩过的坑）

### ① 本机回环请求必须绕开代理（最坑的一条）
WorkBuddy 的终端环境带 `HTTP_PROXY=http://127.0.0.1:5xxxx`。**curl / urllib 默认会把这个代理
用在 127.0.0.1 上**，于是所有本机 API 调用直接 `502 upstream connect failed: Connection refused (os error 61)`。

```bash
curl --noproxy '*' http://127.0.0.1:8765/api/health     # ← curl 必须加
```
`glabs.py` 内部已用空 `ProxyHandler` 处理好了，**但 `.py` 脚本里 `subprocess.run(["curl", …])` 的老写法没有** ——
自己写脚本时要么加 `--noproxy '*'`，要么用 `env={"NO_PROXY": "*", **os.environ}`。
> 症状特征：报错是 `os error 61` 且格式不像 Python —— 那就是代理，不是服务挂了。

### ② key 会随 app 改名/重置而失效 —— 绝不硬编码路径
app 把 key 存在 `~/Library/Application Support/<App Name>/webhook_config.json` → `api_key`。
**唯一真源永远是这个文件**。2026-09-19 改名时 key 从 `gRjd5P…` 换成 `i-fi2a…`，
`~/.hermes/.glabs_key` 没跟着更新 → gateway 全链路 401。

`glabs.py` 的解析顺序（先到先用）：
`--key` → `$GLABS_API_KEY` → `~/.hermes/.glabs_key` → `G-Labs Studio/webhook_config.json` → `G-Labs Automation/webhook_config.json`

**修 key 的一句话**（app 改名/key 重置后跑它）：
```bash
P=~/.workbuddy/binaries/python/versions/3.13.12/bin/python3
$P - <<'PY'
import json, pathlib
h = pathlib.Path.home()
k = json.loads((h/"Library/Application Support/G-Labs Studio/webhook_config.json").read_text())["api_key"]
(h/".hermes/.glabs_key").write_text(k + "\n"); (h/".hermes/.glabs_key").chmod(0o600)
print("glabs key 已同步:", k[:6] + "…")
PY
# gateway 需要重启才重新读 key（它是启动时读一次的）
```
gateway 侧另有两处读取：`~/.hermes/.env` 的 `GLABS_API_KEY`（优先级高）与
`~/.hermes/drama-gateway/providers.ini` 的 `[glabs]` 段（`key_env` → `key_file`）。

### ③ 参考图别走 path —— 走 base64
G-Labs 是 macOS app，读 `~/Documents`、`~/Desktop`、`~/Downloads` 会撞 TCC 隐私限制，
报 `UPLOAD_ERROR Operation not permitted`。**而 vault 本身就在 `~/Documents` 里**，
所以「拿库里的图当参考」是老方案的必经坑。

`glabs.py` 默认 `--ref-mode base64`：图片编码进请求体，app 完全不碰磁盘，**2026-09-19 实测通过**
（用 `Assets/小厚先生/角色设计/3D avatar render.png` 直接放大成功）。
`--ref-mode path` 只在图很大且同机时才有意义（body 上限 50MB，base64 会膨胀 ~33%）。

### ④ 先看图再写 prompt（承接 `drama-claw-hermes` 的两课）
动手前必须有**画面级证据**（项目详情 + ≥2 张图）。标题和封面都不算数。

> ⭐⭐ **但「验收 / 挑片」这一步不要自己读图**（2026-09-24 Seth 明确要求）。
> 原话：「你不要用自己查看去对比了，我自己点开看是一样的。因为自己看要很久啊。」
> · **挑哪张好是审美判断，归他**；我读图既慢又烧视觉 token，
>   **而且我读出来他也看得到 → 同一张图处理两遍 = 纯重复劳动**。
> · **生成完立刻做的事**：用 `_build/make_ab_sheet.py` **拼一张对照表** → `present_files` 推给他 →
>   等他一句「A」/「B」。我这边只做机械活（拼图 / 抽帧 / 算积分差值）。
> · **边界**：**「改 prompt 之前」仍然必须自己看图**（否则是盲改）。
>   收窄的是**验收**这一步，不是「先看图」整条废掉。
>
> 配套工具（都在 `003-Workbench/_build/`，要 Pillow 的用 `envs/default/bin/python`）：
> - `make_ab_sheet.py` —— 多格并排对照表（2/4/6/9 自动排版）→ 给他一眼看完
> - `crop_zoom.py` —— 归一化坐标裁切放大（核「两只耳朵都在吗」这类细节硬判据）
> - `compile_spec.py` —— 「人读 spec」(`common`/`steps`) → 可跑 spec（`frames`/`clips`）；
>   **prompt 永不手抄**（手抄 400–800 字必然静默抄错，而画面照样出得来、结论作废）

### ⑤ 账号：**默认轮换，要可复现就必须钉死**
`flow_accounts.json` 里每号有 `_runtime_uuid`；**不传 `account_id` 时 app 按请求轮流挑号**。

> ⚠️ **2026-09-19 实测修正**：以前写「让它自己挑」—— 现在知道它的挑法是
> **每条请求严格交替**。app 日志特征：不传时 `Shared worker started (accounts=2)`，
> 传了变 `(accounts=1)`。**同一条片子里，镜 1 走 A 号、镜 2 走 B 号。**
> → 想让一条片子可复现，**必须钉死**。（本次实测：钉死后整轮只走一个号，一致性未变差。）

```bash
# 取 uuid（列表里可能不显示，直接读 JSON 的 _runtime_uuid 更稳）
/usr/bin/python3 -c "import json,os;print([a['_runtime_uuid'] for a in json.load(open(os.path.expanduser('~/Library/Application Support/G-Labs Studio/flow_accounts.json')))])"
# 钉死（gen_frames.py / gen_clips.py 都认这个环境变量）
GLABS_ACCOUNT_ID=<uuid> python3 gen_frames.py specs/<x>.json
# 或直接
$P $G image --prompt "..." --account-id <uuid>
```

⛔ **别用 `providers.ini` 里那个 `0d385969-…`** —— 那是**改名前的旧快照**，带着它提交必
`Max Retries Exceeded`（2026-09-19 已注释掉）。

**账号会过期**：`glabs.py accounts` 里 `status=expired` / `last=error` 的号需要**在 app GUI 里重新登录**
（日志特征：`[401 Renew] … renew failed - DISABLED + flagged expired (needs manual Renew / re-login)`）。
这个我从命令行修不了，得你点。

> 💡 注意 `glabs.py accounts` **不显示 `enabled` 字段**。要判断某号是否被停用，
> 得读 `flow_accounts.json` 的 `enabled`。本次实测时池里 2 个号、
> `thepraisepolice` 的 `enabled` 已是 `False`，但**它照样在轮换里被使用** ——
> 说明 webhook 通路不看这个开关。

### ⑥ ⚠️ `--ref` 是 `nargs='*'` —— **重复传 flag 会静默丢图**（2026-09-24 实锤）

`glabs.py image` / `video` 的 `--ref` 接受多个值，但**写成重复 flag 只会保留最后一个**：

```bash
# ❌ 错：只送进去 1 张（ref16-street），xh-back.png 被静默丢弃
$P $G image --prompt "…" --ref a.png --ref b.png
# ✅ 对：一次 flag 传多个值
$P $G image --prompt "…" --ref a.png b.png
```

**验证方法（必做）**：跑 `--dry-run`，看输出里的 `reference_images = N 张`，
N 必须等于你想要的张数。**顺序也要核**：`[0]` 是第一张。

> 🔍 **这个坑差点让我原样重现一个失败实验**：C6 要复现 C1 背影镜时补挂角色 ref，
> 第一版就写成了重复 flag → `--dry-run` 报 `1 张`，等于**没挂**，跑出来必然还是崩的，
> 而我会误判成「加了 ref 也没用，结论不成立」。
> **静默丢参数比报错危险得多 —— 生成类命令一律先 dry-run 数张数。**

## Workflow 节点图 —— ⛔ 已弃用（2026-09-19）

**现状：不要主动推荐这条路线。** Seth 试用后判定 GUI 体验不好 ——
**G-Labs 只走 API 形式**（本 skill 的 `glabs.py` 就是那条正路）。
将来若要「可视化串流程」，他的方向是 **ComfyUI**（以后再说，别自己提）。

以下内容仅作**留档**（万一以后要回头用）：
app 里的可视化流程图（prompt → 图 → 片 → 抽帧 → 再出片 → merge），**只能 GUI 点 RUN FLOW，没有外部 API**。
JSON 我可以离线校验：

```bash
$P $G workflow 003-Workbench/_build/workflows/02-five-shot-reel.json   # 结构校验，不花额度
```

- 已交付三张（单镜 / 五镜成片 / 批量出图）→ 生成脚本 `_build/build_workflows.py`（**均已封存**）
- 详细说明与「首次加载检查清单」见 vault [[G-Labs-Workflow]]
- 校验器已用 app 自带的 `sample/default.json` 做过基准测试

## 和 spec 三件套的关系

`003-Workbench/_build/` 的 `gen_frames.py` / `gen_clips.py` / `assemble_reel.py` 是**spec 驱动**脚本，
默认 `--backend native`（直连 :8765），`--backend gateway` 走 DramaClaw 链路。
`glabs.py` 是**直连原生 API** 的通用入口，适合一次性/探索性生成和不在 spec 里的新能力（grok/meta/openai/upscale）。
**→ 这三条（native / gateway / glabs.py）+ ffmpeg 合成 = 当前唯一在用的生成路线。**

## 排障流程（按顺序）

1. `glabs.py health` —— 服务活着吗？不在就打开 G-Labs Studio app，Webhook 页确认 autostart。
2. `glabs.py key` —— key 来源对不对？跟 `key_source_hint()` 打印的 app 真源比对。
3. `glabs.py accounts` —— 账号有没有过期？（`expired` / `last=error` → GUI 重新登录）
4. 报 `os error 61` → 代理问题（铁律 ①）。
5. 报 `401` → key 失效（铁律 ②）。
6. 报 `Max Retries Exceeded` → 多半是**带有问题的 `account_id`**（铁律 ⑤）或**账号过期**。
7. 报 `403 Webhook requires MAX plan` → app 侧计划到期/在别的机器登录。
8. 报 `429` → 该账号配额满；换账号或换模型。
9. 报 `UPLOAD_ERROR Operation not permitted` → 参考图撞 TCC（铁律 ③，改 base64）。
10. 报错但任务表里有这条 → `glabs.py tasks` 看 `error` / `error_detail` 原文。

## 环境事实（2026-09-19 实测）

| 项 | 值 |
|---|---|
| app | `/Applications/G-Labs Studio.app`（另有 `G-Labs Story Machine.app`） |
| 端口 | `127.0.0.1:8765`（默认，可改） |
| key 真源 | `~/Library/Application Support/G-Labs Studio/webhook_config.json` |
| 产物默认落盘 | `~/Documents/G-Labs Studio`（app 侧）；本 skill 落 `--out` |
| 同族服务 | DramaClaw :8780 · drama-gateway :8790 · 前端 :8080 · Voice Studio :8766 |
| 账号池 | `~/Library/Application Support/G-Labs Studio/flow_accounts.json`（`glabs.py accounts` 读） |
| 实测耗时 | 出图 ~40s/张 · 出片 51–59s/条（6s@720p）· **放大看输出像素**：576²→2304² 用 4.2s，2628×1428→5256×2856 用 32s（本地 GPU，**与 quota 无关**） |
| 实测（2026-09-19 直连） | 出图 1 张 32s ✓ · 出片 1 条 6s@720p 57s ✓ · 放大 4.2s ✓ —— **全走 native 后端，无 account_id** |
