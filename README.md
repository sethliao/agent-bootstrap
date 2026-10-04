# agent-bootstrap

> 你的 agent 环境就是你手艺的延伸。这个仓让它在任何一台机器上**原地复活**——换电脑、换助手（WorkBuddy / Hermes / 别的），都一样。

**一句话**：26 个自写 agent skills + MCP 配置 + 启动脚本 + CLI 来源清单，按「链」组织、靠文件交接、密钥永不进仓。

## ⚡ 30 秒上车

```bash
git clone https://github.com/sethliao/agent-bootstrap.git && cd agent-bootstrap
bash install.sh          # skills + mcp.json + chains 就位，剩下的它提示你
```

装完还差两件手动活：**keychain 写入 API key**（服务名见 [CLI-清单.md](CLI-清单.md)）和**装 CLI**（一条 npm/pip/uv 的事，全在同一张清单）。之后每次会话，agent 按 [chains/REGISTRY.md](chains/REGISTRY.md) 的链路干活。

## 🗺 里面有什么

| 目录/文件 | 是什么 | 规矩 |
|---|---|---|
| `skills/` | 26 个自写 skill（安装单位，平铺进 `~/.workbuddy/skills/`） | 真源改了跑 `sync.sh pull` |
| `chains/` | **链注册表** —— skills 怎么串起来用的唯一真源 | 只改 `REGISTRY.md`，push 即生效 |
| `mcp/` | MCP server 配置（dramaclaw / reach-mcp / gflow） | 装完在 WorkBuddy 里 Trust 一下 |
| `launchers/` | DramaClaw 启动脚本 ×6 | 本地部署在 `~/Code/drama-claw-hermes` |
| `CLI-清单.md` | 网络装的 CLI 来源 + keychain 服务名 | 恢复环境照这张表走 |

## 🧩 Skills 目录（26）

### 生产管线（IP → 成片）

| skill | 一句话 |
|---|---|
| [drama-claw-hermes](skills/drama-claw-hermes/) | 本地 DramaClaw 视频管线操作 |
| [drama-episode-automation](skills/drama-episode-automation/) | 一份 brief → 一集 DramaClaw 成片 |
| [agnes-video-prompt](skills/agnes-video-prompt/) | Agnes Video 2.5 写提示词出片（官方 API / Pavo 网页） |
| [glabs-studio](skills/glabs-studio/) | 直连本地 G-Labs Webhook 出图/出片/放大 |
| [character-ip](skills/character-ip/) | 角色 IP 项目：参考图、角色档案、一致性 |
| [design-codex](skills/design-codex/) | 设计契约（DESIGN.md）约束对外视觉 + AI 味审计 |
| [ep-qa](skills/ep-qa/) | 成片机器体检：画幅/响度/黑帧/一致性，只报可测事实 |

### 调研（只读抓取）

| skill | 一句话 |
|---|---|
| [behance-research](skills/behance-research/) | Behance 搜索/主页/moodboard → 结构化 JSON+CSV |
| [content-research-board](skills/content-research-board/) | B站/小红书/抖音/知乎/微博 → 内容调研看板 |
| [x-bookmarks-mining](skills/x-bookmarks-mining/) | X 收藏/点赞/时间线挖掘与分层 |
| [social-account-diagnosis](skills/social-account-diagnosis/) | 自建/对标社媒账号诊断 + 行动清单 |
| [studio-site-teardown](skills/studio-site-teardown/) | 拆同行站点：定位话术 + 结构 + 真实体量 |
| [library-pull](skills/library-pull/) | WorkBuddy 资料库节点批量取回本地 |
| [gosim-survey-run](skills/gosim-survey-run/) | 本地跑 GOSIM 巡天 agent，拿同源分数细项 |

### 内容与分发

| skill | 一句话 |
|---|---|
| [content-strategy](skills/content-strategy/) | 原创动画 IP 的内容策略（三 IP） |
| [behance-case-deck](skills/behance-case-deck/) | 把 IP 做成能直接发 Behance 的完整案子 |
| [behance-replicate-run](skills/behance-replicate-run/) | 把一条 Behance 参考片复刻跑通成自己的 |
| [social-media-archive](skills/social-media-archive/) | 自己发的帖子全平台归档进 vault |
| [ai-handover-pack](skills/ai-handover-pack/) | 知识库编译成平台中立的交接包（Coze/Kimi/GPTs） |
| [b2b-anchor-proposal](skills/b2b-anchor-proposal/) | To B 洽谈：实查决策链 → 锚定身份 → N 页方案 |

### 工作方法（agent 自身）

| skill | 一句话 |
|---|---|
| [frame](skills/frame/) | 「开工 / 收工」两个开关，状态全在库不靠对话 |
| [new-tool-triage](skills/new-tool-triage/) | 新工具四选一处置：只用 / 扩展 / 包装 / 抄 |
| [mcp-server-verify-mount](skills/mcp-server-verify-mount/) | 验 MCP server 真能跑再挂载 |
| [agent-skills-bridge](skills/agent-skills-bridge/) | 把别的 agent 的 skill 软链桥接进来 |
| [obsidian-auto-context](skills/obsidian-auto-context/) | 会话结论自动沉淀进知识库 |
| [obsidian-plan-workflow](skills/obsidian-plan-workflow/) | 计划驱动执行：审批后才动手 |

## 🔗 链

skills 不单独用，按链串：**口令触发 → 按序调 skill → 文件交接（上一步产物路径 = 下一步输入）→ 门控不过关就停**。
链的定义、改法、现有三条链（生产 / 跑通 / 发布）→ **[chains/REGISTRY.md](chains/REGISTRY.md)**。
两条铁律：一轮 ≤3 个 skill 同时在场；每一环先单独跑通再串。

## 🔄 日常同步

```bash
bash sync.sh push    # 真源(~/.workbuddy/skills) → 本仓（改了 skill 后）
bash sync.sh pull    # 本仓 → 真源（换机器恢复后反向）
git add -A && git commit -m "..." && git push
```

## 📐 设计规矩

1. **密钥永不进仓** —— keychain 是运行时真源，本仓三道扫描零命中才发版
2. **文件交接，不靠对话记忆** —— 链的每一步产物有固定路径，下一步只认文件
3. **真源一处** —— skill 真源在 `~/.workbuddy/skills/`，链真源在 `chains/REGISTRY.md`，本仓是备份 + 分发
4. **「跑过」≠「跑通」** —— 每一环单独验证过才准进链

## License

[MIT](LICENSE) © Seth Liao
