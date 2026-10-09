---
name: gosim-survey-run
description: 在本地跑 GOSIM「巡天智能体 / Agentic Observer」黑客松的 agent，拿到与平台同源的分数细项，并定位分数丢在哪。当用户说「跑一下 GOSIM」「巡天智能体跑分」「黑客松分数」「L1/L2/L3/L4 卡」「练习卡 α」「GOSIM 提分」「看看 agent 多少分」时使用。
agent_created: true
---

# GOSIM 巡天智能体 · 本地跑分与诊断

**回答一个问题：agent 现在多少分，丢的分丢在哪一项？**

配套作战计划 → vault `002-Areas/GOSIM-黑客松-巡天智能体.md`（赛制 / 得分公式 / 基线实测 / 提分清单）
**一切细节以那份文档为准；本 skill 只管「怎么跑、怎么看」。**

---

## 0. 先确认（30 秒）

| 事实 | 值 |
|---|---|
| 官方仓落地 | `~/Code/gosim-survey26`（**库外** —— 带 `.git` 的 84MB 仓不进 Obsidian 同步目录） |
| 跑分入口 | `examples/_local/runner/run_local.py`（**`verify_engine.py` 校验过 = 与平台字节一致**） |
| 离线练习卡 | `examples/_local/cards/L1–L4`（**带 truth，完全不联网**） |
| Python | `~/.workbuddy/binaries/python/versions/3.13.12/bin/python3`（**纯标准库，零依赖**） |

若仓库不在 → `git clone https://github.com/gosimfoundation/hackathon-survey26.git ~/Code/gosim-survey26`

---

## 1. 跑一张卡（7 秒）

```bash
bash ~/.workbuddy/skills/gosim-survey-run/run_card.sh L4
```

脚本等价于（手敲也行）：

```bash
cd ~/Code/gosim-survey26
PY=~/.workbuddy/binaries/python/versions/3.13.12/bin/python3
export OPENAI_API_KEY=local-debug-no-llm OPENAI_BASE_URL=http://127.0.0.1:9/v1
$PY examples/_local/runner/run_local.py --inherit-env \
   --card examples/_local/cards/L4 \
   --agent "$PY agent.py" --agent-cwd examples/python --out run_output/L4
```

四张卡全跑一遍：`for c in L1 L2 L3 L4; do bash .../run_card.sh $c; done`（⚠️ zsh 里写字面量，别用变量展开）

**产物**（`run_output/<卡>/`）：`decisions.csv` · `observations.csv` · `score_report.json` ·
`workflow_result.json` · `messages.jsonl` · `agent.log`。

---

## 2. 关键技巧：占位 key 就能跑

`agent_core/llm_client.py` 的 `require_api_key()` **只检查非空、不做校验**（不 ping 服务端）。

→ **没有真 key 也能出分**：给 `OPENAI_API_KEY=任意非空串` + `OPENAI_BASE_URL` 指向不可达地址
（`http://127.0.0.1:9/v1`），LLM 调用 3 次即 `HTTPError` 失败被**静默跳过**，
`agent.log` 里写 `fell back`，**确定性规划器照常跑完**。

⚠️ 但要分清两件事：
- **本地出分** —— 占位 key 足够。
- **评奖资格** —— 硬门槛要求 **≥2 个环节由大模型驱动**（组织方靠 Claude 读最终版代码判定）。
  占位 key 跑出来的分**是纯确定性基线，不含任何 LLM 加分**。要真跑 LLM：把
  `OPENAI_BASE_URL`/`OPENAI_API_KEY`（Kimi Coding Plan：`https://api.kimi.com/coding/v1`，model `k3`）
  写进 `examples/python/.env`，并**不要**加 `--inherit-env` 覆盖。

---

## 3. 看分：`score_report.json` 里只有两处有料

```
components = { sum_best_scores, required_penalty, uniformity_penalty,
               report_settlement, observation_request_reward }   ← 分数构成
counts     = { decisions, observations, observe_actions, targets_observed,
               required_missing, invalidated_observations,
               observation_requests_issued / _completed }        ← 实际干了什么
```

`total = sum_best_scores + required_penalty + uniformity_penalty + report_settlement + observation_request_reward`
（顶层还有 `termination`、`uniformity_bands`（按 10° 赤经带的完成率）、`by_class`（按目标类别）。）

另外 stdout 最后一行还有 `wall_seconds` / `runner_seconds` / `termination_reason`。

---

## 4. 诊断口径（按「可捡分数 ÷ 改动量」排）

跑完先问这四句，**不要凭感觉**：

| 症状 | 看哪个字段 | 钱在哪 |
|---|---|---|
| **故障上报漏了？** | `components.report_settlement` | 每张卡都有 **1 次 `instrument_fault`**（`truth/v4_events.csv`，scope=ALL，效率掉到 0.44–0.65）。**报对 +100**，`false_report_free_allowance=2`（错报两次内免罚）→ 报得越早越赚。**0 = 整块丢了** |
| **限时请求没捡？** | `counts.observation_requests_completed / _issued` | 每卡 2 个请求、每个 `completion_reward=100`（8 个目标里完成 ≥6 个才算）。示例策略是"只做 tie-break、绝不主动追" → 常年 **0/2** |
| **REQUIRED 漏了？** | `counts.required_missing` × `score_config.required.penalty_per_missing`（=50） | 门槛是 `observed_factor_threshold=0.5`，**且程序倍率不能用来凑门槛** |
| **分布偏了？** | `components.uniformity_penalty`（= `200×(1−J)`） | 看 `uniformity_bands` 里哪几条赤经带特别低；**通常不是主要矛盾**，排最后 |

**结论写法**：给一张「四卡 × 分项」对照表 + 每条失血一句「为什么」（能指回 `truth/` 里的证据），
量化成"还能捡多少分"。**不要写"性能有待提升"这种没有数字的话。**

---

## 5. 提交仓（参赛用）—— 别跟跑分仓搞混

⭐ **提交给平台的是这个**：[sethliao/gosim-survey26-agent](https://github.com/sethliao/gosim-survey26-agent)
（本地 `~/Code/gosim-survey26-agent`，**公开仓**）。

| | 跑分仓 | 提交仓 |
|---|---|---|
| 路径 | `~/Code/gosim-survey26` | `~/Code/gosim-survey26-agent` |
| 是什么 | 官方整仓（平台+评分器+离线卡），**只读用** | **我们的参赛项目**，只含 agent |
| 干什么 | 本地跑分出分 | 推上去，平台快照这个 revision |

**改完 agent 要推两个地方**：新代码先进提交仓 `git commit && git push`（平台快照的是**远端 revision**，不是本地文件）；
想本地验证就先在跑分仓用 `--agent-cwd ~/Code/gosim-survey26-agent` 跑一遍。

⛔ **key 绝不进提交仓**：`.env` 已被 `.gitignore` 挡掉，**平台还会主动拒绝含 `.env` 的 ZIP**；
运行时由平台注入它自己的模型代理 + 临时凭据（scoped credential）。

⚠️ **许可证**：示例本体是 **CC BY-NC 4.0**（组织方材料 → 必须署名，`LICENSE` 里已点名来源）。
组织方原文：「**不适用于参赛者自己写的代码**」→ 我们自己新写的部分不受这条约束。

⚠️ **评奖门槛**：要求 **≥2 个环节由大模型驱动**（组织方主要靠 Claude 读最终版代码判定）。
官方示例自带 3 处（预报推理 / 公告+命中率自诊断 / 故障确认）→ **别为了"简单"把 LLM 砍掉，那是直接弃权。**

### 平台提交：三步走（⚠️ 贴链接 ≠ 一键出分）

页面 `create.gosim.org/survey26/platform/compete`：

| 步 | 动作 | 计不计评测次数 |
|---|---|---|
| 第1步 · 上传项目 | 项目名 + 公开仓库 URL → 「上传并准备」 | 每天 10 次，**不占** |
| 第2步 · 检查并确认版本 | 等准备完 → 「检查接口」核对运行设置/适配代码 → **确认版本** | **不占** |
| 第3步 · 开始评测 | 「开始评测」→ 全场景各跑一遍，**取平均**；榜上取本队最高 | ⚠️ **占当天 1 次** |

配额以**页面上的活数字**为准（历史上是 8 次/天，文档里的 5 次是旧数），UTC 0:00 / 北京 8:00 重置。

### 「模型 API（可选）」怎么填（官方在页面上直接给了）

只有**会调用大模型的项目**才要填；提交阶段不需要 key。填了之后平台会在**跑评测时**注入
`OPENAI_BASE_URL`/`OPENAI_API_KEY`（它自己的代理 + 临时凭据）——所以 key 永远不进仓库。

```
协议     → OpenAI 兼容（/v1/chat/completions）        ← 默认，别改
API 地址 → https://api.kimi.com/coding/v1            ← 组委会发放的 Kimi Coding Plan
模型     → kimi-for-coding（或 k3）
API 密钥 → 你的 Kimi key
模式     → 加密保存在服务器上（默认）                  ← 务必选这个
```

⚠️ 别选「不保存（页面中转）」：那种模式**每次评测都要保持页面一直开着**，关页面 = 模型调用失败。
⚠️ 页面底部原话：「**不要把永久密钥放进仓库或 ZIP。**」

### 第2步「检查接口」抽屉里有什么

点「检查接口」会展开一个抽屉，平台在这里告诉你它到底怎么跑我们的项目 —— **这份内容值得逐条核对**：

| 项 | 说明 |
|---|---|
| 公开场景测试 | 应显示「通过」。**这是接口协商成功的唯一硬证据** |
| 适配说明 | 自带 `observer.project.json` 的项目应显示 `Project supplies its own JSON-Lines interface.` |
| 新增的适配文件 | 应为「无」。**若平台生成了适配代码，说明它没认出我们的 manifest，要停下来查** |
| 原始代码指纹 | sha256，可用于确认平台快照的正是我们推的那一版 |
| 运行设置 | 解析后的 `image`（把 `python:3.12-slim` 解析成固定 digest）· `run` · `build` |
| **设计奖材料** | 「架构和复现说明」textarea（**上限 8000 字**）+「代码或文档链接（选填）」→ 「保存材料」。**不影响成绩** |
| 自查框 + 「确认版本」 | ⚠️ 必须先勾选「我已检查运行设置和适配代码」才能点确认 |

⚠️ **刷新页面会把自查框重置为未勾选** —— 点「确认版本」前记得重新勾上。
⚠️ 提交稿要**留一份在库里**，因为里面写着「算法未作改动」之类的话，**改了算法就必须同步改稿**。

### 用 opencli 填平台的坑（踩过）

- ⚠️⚠️ **视口外的元素点不到** —— `click` **不会自动滚动**。先量 `getBoundingClientRect()`：
  `top` 必须在 `0 ~ window.innerHeight` 之间，否则点击会落到别处（**而且仍返回 `clicked: true`，骗你**）。
  然后 `scroll down` **小步长**反复滚（默认 500 或 `--amount 400`）。
  ⚠️ **大步长（如 4000）会 `cdp_timeout`**；`eval window.scrollTo(...)` 会被拒（`command_result_unknown`）。
- ⚠️ **会话会中途变哑**：`command_result_unknown` / `detached_mid_command` / `eval` 返回 `undefined`。
  此时 `opencli doctor` **仍然是全绿的** —— doctor 绿 ≠ 会话健康。**直接 `open` 一个新会话**（换个 session 名）即可。
- ⚠️ **有些点击干脆交给 Seth 自己点** —— 比自动化更快更稳，尤其页面深处的按钮。我们的价值在"把页面开好、滚到位、告诉他点哪个"，不在"替他点"。
  一条现成的可靠路径：`open -a "Google Chrome" "<url>#<section-id>"`（页面里 `<h2 id=evaluate>` 这类锚点可用）。
- ⚠️ **ref 会随每次 `state` 刷新而变**，隔了一条命令的旧 ref 拿去 `fill` 会报 `not_editable`。
  稳妥做法：**用 CSS 定位再操作**，比如 `find --css "textarea"`（页面上通常只有唯一一个）。
- ⚠️ **长文本不要直接塞进命令行**：先写文件，再 `fill <ref> "$(cat /tmp/xxx.txt)"`，避开 shell 转义。
  含 `` ` ``、`$`、引号的正文这样走最稳。
- ⚠️ **`type` 会逐字模拟键盘，`fill` 是精确设值并回验** —— 填长 textarea 用 `fill`。
- ⚠️ **填完必须回验**：`get value <target>`，或用 `eval` 读 `document.querySelector('textarea').value.length`。
- ⚠️ **"页面上显示着" ≠ "服务器存下了"**：保存后**整页刷新、重开抽屉**再验一次。
- ⚠️ `browser network` 可能捕不到请求（缓存为空）→ 别指望它，直接刷新回验更可靠。
- 🔐 **要填密钥时**：密钥只从**文件读进 shell 变量**再传参，**绝不出现在命令行文本里**；
  输出统一过一遍 `sed -E 's/(sk-)[A-Za-z0-9_-]{6,}/\1****[REDACTED]/g'` 打码；
  事后 grep 复核 vault 里没有 key 片段。**用户不需要把密钥发给你**。

### 想读平台页面时（Seth 已经打开那个标签页）

```bash
export PATH="$HOME/.local/bin:$PATH"
opencli browser gosim bind                       # 绑他已打开的标签页
opencli browser gosim state                      # 页面结构 + [N] 可交互元素
opencli browser gosim get text "<css选择器>"      # 抓某段原文
opencli browser gosim unbind                     # 用完释放
```

## 6. 读排行榜 / 提分优先级

**练习赛 = 云端把 α β γ δ 四张卡全跑一遍、分数取平均**；每日 8 次；**榜上取本队最高一次** → **跑砸不掉分，放心迭代**。

排行榜列名与含义（读榜别只看总分）：

| 列 | 含义 | 怎么用 |
|---|---|---|
| 总分 | 榜上排的就是它 | — |
| **最佳得分** | **基础科学分**（扣罚之前） | 与头部比这一列，才知道差距是「结构问题」还是「本事问题」 |
| **必观测惩罚** | 漏掉的 required × 50 | ⭐ **最容易捡，先看它** |
| 报告结算 | 故障上报净得失（对 +100 / 错 −150） | `0` = 一次都没报成功 |
| 均匀性惩罚 | `200 × (1 − Jain)` | 通常不是主要矛盾，排后面 |
| 限时观测请求 | 请求奖励 | 示例策略**故意不追** → 常白丢 |
| 观测目标 / REQ 缺失 | 实际观测目标数 / 漏掉的必需目标数 | 与头部比「观测目标」，看是不是在少观 |

**提分顺序（性价比）**：① 必观测守门槛 → ② 故障上报放宽 → ③ 主动追限时请求 → ④ 均匀性 → ⑤ 才轮到基础科学分。

⚠️ **「报告结算 0」不要想当然归因于"没配模型 key"** —— 上报是 **fail-open** 的，模型缺席也照报（`decision_source="rule"`）。
先查规则门槛：`REPORT_DROP`（默认 0.62）· `REPORT_CONFIRMATIONS`（需连续确认次数）· `REPORT_SPACING_HOURS` · `MAX_REPORTS`。

⭐ **本地迭代口径**：官方就是用示例包里的 `local-cards/`（= L1–L4）离线跑分的，而且明确警告
「**不要照着某张卡的天气或目标把策略写死**」→ **改动必须在四张卡上都变好**，只有一张变好 = 过拟合。
（所以**不必**非等 α–δ 的 ZIP —— 那个下载按钮在后台标签页里点了不落地。）

⚠️ 官方「常见错误」清单，改之前逐条对一遍：
日志打到 stdout · `decision_sequence` 错或加未知字段 · **每次决策都调 LLM** ·
**对暗目标用短曝光（多次曝光不累加，只取最好一次）** · 在警告方向指低仰角 · **一次曝光变差就报故障**

## 7. ⛔ 已证伪的三条路线（2026-10-04 凌晨 · 四卡交叉验证实测，别再重踩）

> 基线 = 官方示例原样 = **四卡 4,250.75**（无 LLM）。三个实验全灭，参赛仓已回滚。

| 实验 | 改动 | 结果 | 死因 |
|---|---|---|---|
| **放宽故障上报** | `REPORT_DROP` 0.62→0.75 · `REPORT_CONFIRMATIONS` 3→2 · `REPORT_SPACING_HOURS` 6→3 | **−414.61** | L2 在真故障前 6 天就**误报**（drop 波动被当成故障）→ 用完 `MAX_REPORTS`；且 `forget_quality_history()` **清空质量历史** → 真故障再也报不出，观测策略失参照 → required 漏 4→15。**误报代价不是 −150，是连锁崩盘** |
| **钳制 `duration_scale ≥ 1.0`** | 拒绝模型缩短曝光 | L1 **−583** | **方向错了**：曝光缩短 = 更多指向 = 更高覆盖（动作 593→496、目标 5,307→4,924） |
| **加更短曝光档** | `DURATIONS` 加 180/240 | **−253**（四卡全跌） | 新覆盖的是低权重目标；还打坏上报判定 |

⭐ **两条硬结论**：
1. **云端同代码两次评测可差 ±200**（18:05 = 3,790.60 vs 23:17 = 3,613.98，差在 β −275 / δ −490）。
   确定性部分零方差（本地四卡分数一字不差）→ **波动 100% 来自 LLM**。
   ⇒ **榜上取最高一次 ⇒ 多跑几次评测就是最划算的提分手段**（零成本零风险）。
2. **「LLM 帮倒忙 −144」是错的**。真 key 跑 L1 = **4,501.44** > 无 LLM 4,458.56（**+42.88**）。
   LLM 输出分布本来就偏短（`x0.70`×9 / `x0.85`×6 / `x1.00`×10 / `x1.05`×3），**方向是对的**。LLM 必须留着（评奖门槛）。

⚠️ **改 `planner.py` 任何常量之前，先读紧邻的那段长注释** —— 官方把试过并否决的激进设计写在里面（`REQUEST_RATE_TOLERANCE` 上方 16 行），比任何外部分析都硬。

## 8. 要测 LLM 相关的改动：必须用真 key 跑（本地 7 秒法测不出来）

占位 key 时 `state.duration_scale` 恒为 1.0（LLM 静默失败）→ **任何动 LLM 输出的改动在本地等于没改**。

```bash
# 1) 真 key 写本地 .env（已被 .gitignore 挡掉，⛔ 绝不进仓）
#    DeepSeek 官方 key 是 35 字符 sk-xxxx(32)；51 字符那些是硅基流动等别家，别抓错
printf 'OPENAI_BASE_URL=https://api.deepseek.com\nOPENAI_MODEL=deepseek-flash\nOPENAI_API_KEY=<35字符key>\n' \
  > ~/Code/gosim-survey26-agent/.env && chmod 600 ~/Code/gosim-survey26-agent/.env
# 2) ⛔ 不加 --inherit-env（否则宿主占位 key 会覆盖 .env）
cd ~/Code/gosim-survey26 && $PY examples/_local/runner/run_local.py \
  --card examples/_local/cards/L1 --agent "$PY agent.py" \
  --agent-cwd ~/Code/gosim-survey26-agent --out run_output/X_L1
```

⏱ **耗时**：无 LLM **7 秒/卡**；**真 LLM 约 190 秒/卡**（32 晚 × 2 次调用 × ~0.8s）。
若改了 `DURATIONS` 让指向变多，单卡可涨到 **3–4 分钟**（四张 = 12 分钟）→ 放后台跑，别卡前台超时。
💡 只关心「LLM 到底给了什么」时，**不要跑整卡**：`grep -o "duration x[0-9.]*" <out>/agent.log | sort | uniq -c` 就有分布。

## 9. 坑（踩过）

- ⚠️ **仓库里有两套卡，别搞混**：
  `examples/_local/cards/L1–L4` = **离线练习卡（带 truth）**；
  `cards/v4-practice-alpha…delta/card.json` = **平台练习卡 α–δ 的参数表**（`config/`+`public/`+`truth/` **在平台 Resources 页**，仓库里没有数据）。**两套不是同一批卡。**
- ⚠️ **`--card` 只按 `L1..L4` 去 `runner/` 的【父目录】下找**，而实际卡在 `cards/` 子目录 →
  **一律传显式路径** `examples/_local/cards/L4`，不要图省事写 `--card L4`。
- ⚠️ **README 讲的是 challenge v3，实际卡全是 v4**（`v4_*.json`）→ 以卡里的 `schema_version` 为准，别被 README 带偏。
- ⚠️ **zsh 不对未加引号的变量做词分割** → 批量跑四张卡要写字面量列表，别写 `for c in $LIST`。
- ⚠️ **提交镜像 `python:3.12-slim` ≠ 本机 3.13** → 本地能跑不代表提交能跑（但链条纯标准库，风险低）；提交前过一遍兼容。
- ⚠️ **`DURATIONS` 加短档真的会生效**：卡的 `exposure.min_duration_seconds = 60`，不是 300。
- ⚠️ **同代码两次云端评测可差 ±200**（LLM 抽签）—— 报成绩前先确认代码没变，别误判成"改坏了"。
- ⚠️ **对外/上传/建仓/花 credit** 一律先出 plan 给 Seth 点头（红线）。本地跑分不需要点头。
