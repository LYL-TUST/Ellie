# Ellie — 带自建评测体系的终端 Coding Agent

`ellie` 是一个在终端里跑的轻量 coding agent：给它一个任务，它会自己读代码、搜文件、改代码、跑命令，每一步都留记录。**更重要的是，它带了一套可复现的评测体系——每个机制改进都有消融实验和量化收益，不听模型自述、看最终产物。**

- 纯标准库 Python 实现，~7,300 行，零外部依赖
- 支持 DeepSeek / OpenAI / Anthropic / Ollama / vLLM 五类模型后端
- 本地优先：数据不出终端，所有运行工件落盘可审计

## 为什么做这个项目

市面上的 agent 产品大多在回答"能不能干活"，很少回答另一个同样重要的问题：

> **改了一个机制，怎么知道 agent 是变好了还是变坏了？**

Agent 的日常痛点也都与此相关：

- 模型最后一句"完成了"不可信——没有独立机制验证改动真的生效
- 多轮任务里上下文线性膨胀，token 成本失控，粗暴截断又会裁坏当前请求
- 长任务中断后恢复，最大的风险是**误信过期的旧状态继续执行**
- 模型反复读同一文件、重复确认已知事实，每一步都是浪费

Ellie 对这些问题的回答是同一条产品原则：**能变成确定性代码的环节，绝不交给模型"自觉"。**

## 核心产品决策

| 决策 | 备选方案 | 为什么这么选 |
|---|---|---|
| 上下文按优先级四分区裁剪（prefix / memory / history / request） | 滑动窗口截断 | 滑窗不知道哪些历史重要，可能裁掉关键决策甚至裁坏当前请求；分区后当前请求永远最后动 |
| 审批档位 ask / auto / never 用户可配置 | 写死一种安全策略 | "放行尺度"是用户的风险偏好，不是技术参数——自己的仓库想 auto 提效，陌生仓库需要 ask 兜底 |
| 独立 verifier 校验最终工作区状态 | LLM 自评（LLM 评 LLM） | 裁判和运动员不能是同一个模型；文件状态、测试是否通过才是硬证据 |
| 分层记忆 + promotion / rejection 规则 | 全量塞 prompt / 无记忆 | 全量塞 = token 爆炸，无记忆 = 重复劳动；rejection 规则防止临时状态和敏感信息被误提升为长期记忆 |
| 纯标准库、零外部依赖 | 引入 agent 框架 | 每一行都可审计、可迁移，不被框架版本绑架；也倒逼把 agent loop 每个环节真正搞懂 |
| 五类后端环境变量切换 | 锁定单一供应商 | 不锁供应商，也让消融实验不被单一模型表现污染 |

## 量化结果

> 以下均为固定 benchmark / 消融实验数据（非线上流量统计），结果落盘于 [`benchmarks/results/`](benchmarks/results/)，含复现命令与数据来源说明，可一键复跑。

| 模块 | 实验 | 结果 |
|---|---|---|
| 上下文治理 | 12 组长上下文压力配置 | 平均压缩 **16.4%**（最高 33.6%），当前请求保留率 **100%**，零裁坏 |
| 分层记忆 | 12 题 × 5 次重复，开/关/无关记忆三组对照 | follow-up 阶段重复读文件 **60 → 0**，工具步数 1.0 → 0，正确率保持 100% |
| 断点恢复 | 10 场景 × 3 次重复 | workspace 漂移识别 **6/6**，误信过期状态 **0 例**，resume 成功率 90%（失败项均为无 checkpoint 场景下的预期安全拒绝） |
| 运行时回归 | 12 个固定任务 | pass rate **100%**（12/12） |
| 工程质量 | — | **131** 个测试用例覆盖核心路径与边界情况 |

## 评测体系：四层独立证据

1. **Harness regression**（12 题）——固定回归任务，验证安全、审批、checkpoint 等地基不因改动退化。用脚本化模型输出测的是 runtime 合同稳定性，不混入模型能力评估。
2. **Context ablation**（12 组配置）——上下文裁剪的收益与代价，硬约束是"当前请求零损坏"，压缩率是约束下的优化目标。
3. **Memory ablation**（12 题 × 5 次）——除了开/关记忆，还加入"塞入无关记忆"的对照组，证明收益来自**按需召回的相关性**，而不是"记忆越多越好"。
4. **Recovery ablation**（10 场景 × 3 次）——恢复边界正确性：系统宁可**正确拒绝恢复**，也不带着不完整状态硬跑（fail-safe）。

每道题配独立确定性 verifier，检查最终工作区状态而非模型自述；每次运行落盘 `task_state.json` / `trace.jsonl` / `report.json` 三类审计工件，可回查、可复现。

## 截图

### 架构概览

![Ellie 系统架构](assets/architecture.svg)

### 终端交互

![ellie 终端截图](assets/screenshots/ellie-terminal.png)

## 适合做什么

- 在本地仓库排查测试失败，定位根因
- 读取项目结构，给出修改方案
- 基于现有代码小步迭代，而不是脱离仓库空想
- 会话持久化，支持 `/resume` 恢复上次中断的工作

## 快速开始

需要 Python 3.10+。

```bash
# 推荐：用 uv
uv sync

# 或者 pip 可编辑模式
pip install -e .
```

```bash
# 在当前仓库启动交互模式
uv run ellie

# 指定工作目录
uv run ellie --cwd /path/to/another/repo

# 一次性任务
uv run ellie "帮我排查测试失败的原因"

# 恢复上次会话
uv run ellie --resume latest
```

## 模型后端

ellie 启动时读取项目根目录的 `.env`（参考 [`.env.example`](.env.example)）。配置优先级：

```
显式 CLI 参数 > .env 里的 ELLIE_* 变量 > 旧环境变量 > 代码默认值
```

Provider 选择：

```
--provider > ELLIE_PROVIDER > 默认 deepseek
```

### 推荐：DeepSeek

最小配置只需 key：

```bash
ELLIE_DEEPSEEK_API_KEY="your-api-key"
```

默认模型和接口：

```bash
ELLIE_DEEPSEEK_API_BASE="https://api.deepseek.com/anthropic"
ELLIE_DEEPSEEK_MODEL="deepseek-v4-pro"
```

### 其他后端

```bash
# OpenAI-compatible
uv run ellie --provider openai

# Anthropic-compatible
uv run ellie --provider anthropic

# 本地 Ollama
ollama serve
ollama pull qwen3.5:4b
uv run ellie --provider ollama --model qwen3.5:4b

# vLLM（OpenAI Chat Completions 兼容）
uv run ellie --provider vllm
```

## 工具列表

| 工具 | 说明 | 风险 |
|---|---|---|
| `list_files` | 列出工作区文件 | 低 |
| `read_file` | 按行号读取文件 | 低 |
| `search` | 用 rg 或简单回退搜索代码 | 低 |
| `git_diff` | 查看 git 工作区变更 | 低 |
| `run_shell` | 在仓库根目录执行 shell 命令 | 高 |
| `write_file` | 写入文本文件 | 高 |
| `patch_file` | 精确替换文件中的一个文本块 | 高 |
| `delegate` | 启动只读子 agent 做调查 | 低 |

## 安全

ellie 不会默认放行所有操作。所有工具调用必须经过统一执行闸口：参数校验 → 审批控制 → 重复拦截 → 敏感信息脱敏，模型无法绕过。文件操作路径锚定在 workspace root 之下。

审批档位：

- `--approval ask` — 每次高风险操作前询问（默认）
- `--approval auto` — 自动放行
- `--approval never` — 拒绝所有高风险操作

每次运行后，`.ellie/runs/<run_id>/` 下会写出：

- `task_state.json` — 任务状态和步骤记录
- `trace.jsonl` — 逐事件执行时间线
- `report.json` — 最终运行摘要和指标

## 常用交互命令

- `/help` — 查看内置命令
- `/memory` — 查看提炼后的工作记忆
- `/session` — 查看当前会话文件路径
- `/reset` — 清空当前会话状态
- `/exit` / `/quit` — 退出

## 指标口径与局限

- 上述数据是固定 benchmark / 消融实验结果，样本量分别为 12 题、12 组配置、12 题 × 5 次、10 题 × 3 次；结论仅在这些任务范围内成立。
- harness regression 只证明 runtime 合同稳定，不证明模型 provider 的能力上限；三层消融只证明模块收益，不与模型表现混写。
- 复现方式见 [`benchmarks/results/`](benchmarks/results/) 内的 `DATA_PROVENANCE.md`。

## 开发

```bash
uv run pytest tests -q
uv run ruff check ellie tests scripts
```

代码按边界拆分：`ellie/evaluation/` 放 benchmark 和 metrics，`ellie/providers/` 放模型后端适配，`ellie/features/` 放可选运行时能力。
