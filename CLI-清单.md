# CLI 清单（网络安装的 → 来源地址）

> 原则：**我们写的进本仓，网络装的记来源**。新机器按这张表一条条装回来。
> 实查日期：2026-10-05

## 必装（日常管线依赖）

| CLI | 用途 | 安装 |
|---|---|---|
| **opencli** | 170+ 站点适配器（内容调研主力） | `npm i -g @jackwener/opencli`（实装 1.8.8） |
| **gallery-dl** | 社媒全量归档（+ `--cookies-from-browser chrome`） | `pip install gallery-dl` |
| **gflow-cli** | Google Flow 交付通道 | `uv tool install gflow-cli` · skills 源 = [ffroliva/gflow-cli](https://github.com/ffroliva/gflow-cli) |
| **uv / uvx** | Python 工具运行器（reach-mcp 依赖） | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **reach-mcp** | 无浏览器抓取备用源 | `uvx reach-mcp`（首次运行自动装） |
| **Obsidian CLI** | 库操作（rename/backlinks/bookmarks…） | **随 Obsidian.app 自带**，装 App 即有（`/usr/local/bin/obsidian`） |
| **DramaClaw** | AIGC 视频引擎（本地部署） | fork：[sethliao/dramaclaw](https://github.com/sethliao/dramaclaw) · 本地部署在 `~/Code/drama-claw-hermes`（launcher 在本仓 `launchers/`） |

## 按需装

| CLI | 来源 |
|---|---|
| arkcli（火山方舟） | `npm i -g @volcengine/ark-cli`（自带 24 个 arkcli-* skills） |
| mcp-obsidian | `uv tool install mcp-obsidian` |
| instaloader | `pip install instaloader` |

## 本地 skills 的链接关系（`~/.workbuddy/skills/` 里的软链指向）

| 指向 | 说明 |
|---|---|
| `@jackwener/opencli/skills/opencli-*` | 随 opencli 包安装（6 个） |
| `@volcengine/ark-cli/skills/arkcli-*` | 随 ark-cli 包安装（24 个） |
| `~/.claude/skills/hyperframes*` `media-use` | HyperFrames 插件体系（9 个） |
| `~/.agents/skills/dbs*` | 小红书 dbs 工具族（10 个） |
| `~/.hermes/profiles/...` | Hermes 遗产：flow-music / opencode / flow-agent-pipeline（3 个） |
| `~/.local/share/gflow-cli-repo/skills/` | gflow-cli 的 skills（git clone 自 [ffroliva/gflow-cli](https://github.com/ffroliva/gflow-cli)） |

## keychain 服务名（恢复时逐个写入）

| svc | 内容 |
|---|---|
| `agnes-ai` / `agnes-ai-2` | Agnes API key ×2（双账号双限流池） |
| `cloudinary` | `key:secret:cloud_name` |
