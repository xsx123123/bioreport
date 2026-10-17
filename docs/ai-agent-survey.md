# AI 解读 Agent 可行性调查报告

> 日期：2026-10-17 · 范围：BioReport 现有 AI 管线（`bioreport/pipeline.py`、`bioreport/ai/engine.py`、`bioreport/utils/consolidate_rna_seq_data.py`、`templates/shared/AI.qmd`）

## 1. 需求回顾

原设想：AI 对报告**每个模块**分别解读；模块包含图片时**图文一起解读**；**不把完整基因表达矩阵**发给模型；在现有框架中加入一个 agent，用提示词 + 少量工具完成报告解读，结果嵌入报告。

## 2. 现状盘点（代码证据）

| 环节 | 现状 | 位置 |
|---|---|---|
| 触发 | `"ai"` 模块 + `ai.enabled`，Quarto 渲染前执行 | `pipeline.py:run_ai_pipeline` |
| 数据整合 | 按配置顺序读 DEG/富集 CSV/TSV → Markdown，`deg_limit`(20)/`enrichment_limit`(10) 截断，产出 `data/consolidated_rna_seq_data.txt` | `consolidate_rna_seq_data.py` |
| 模型调用 | 所有 provider 统一通过 OpenAI Python SDK；`volcengine`/`aliyun` 使用内置兼容地址，其他服务商通过 `base_url` 接入；tenacity 重试、`fallback_providers` 降级、`max_input_tokens` 截断、`pricing` 计价 | `ai/engine.py` |
| 回填 | 结果复制为 `data/consolidated_rna_seq_report.md`，`AI.qmd` include 嵌入 | `pipeline.py` + `templates/shared/AI.qmd` |
| Prompt | 单一全局 prompt（`utils/prompt.txt`），一次调用产出整份解读，三段式（QC/DEG/Enrichment） | `prompt.txt` |
| 图片 | 仅在 HTML/PDF 渲染阶段导出静态 SVG（`render_output.py`）；AI 阶段**完全拿不到图** | `render_output.py` |
| 语义块 | 已有 `FigureBlock`/`TableBlock` 模型与 QMD 执行期记录（`report/recording.py`，jsonl），但 AI 管线未消费 | `report/model.py`、`report/recording.py` |
| 表达矩阵 | 从未进入 AI 输入（整合器只读 DEG/富集结果文件）——隐私约束**已天然满足** | 整合器逻辑 |

**结论：现状是"单次调用、纯文本、一次性生成整份解读"，与"逐模块 + 图文 agent"的目标差距有三处：① 无图片输入通道；② 无逐模块调度；③ 无工具调用回路。**

## 3. 差距分析

### 3.1 图片不可得（最大缺口）
AI 在 Quarto 执行**之前**运行，此时图还不存在。可行解法（按侵入度排序）：
- **A（推荐）**：AI 阶段直接调用 `omics/rna/analysis` 的绘图函数，用现有 `print_theme.export_vector` / `panel.to_image(format='png')` 导出 PNG 到临时目录，随请求以 base64 data-URI 发给视觉模型（`engine.py` 已有 `_encode_file`，Ark 与 OpenAI 兼容接口均支持 image content part）。
- B：改为"两段式"——先渲染报告记录语义块，再跑 AI 回填，二次渲染。改动大、渲染翻倍，不推荐。

### 3.2 无逐模块调度
`registry` 已提供模块清单（含标题/别名/父子关系）。新增 agent 循环即可按选中模块迭代，而非一次性输出。

### 3.3 无工具回路
`_call_provider_internal` 目前固定传 system+user 且不回传 tool 消息。OpenAI 兼容接口与 Ark 均支持 `tools`/`tool_choice`，改造点集中在该函数。

## 4. 推荐架构：最小 Agent（`bioreport/ai/agent.py`）

```text
run_ai_pipeline
  └─ InterpretationAgent( engine, config )
       ├─ 工具集（4 个即可）
       │    read_table(path, rows)        # 读 DEG/富集 TSV，限行
       │    get_project_meta()           # 项目元数据 JSON
       │    render_figure(module_id)     # 调 analysis 绘图→PNG→base64
       │    write_section(module_id, md) # 落盘各模块解读
       └─ 循环：for module in selected_modules:
             prompt = 模块专属提示词(来自 prompt 模板目录)
             engine 调用（带 tools，最多 N 轮）
       最终 write_section 结果按模块序拼接 → consolidated_rna_seq_report.md
```

要点：
- **提示词**：`prompt.txt` 拆为 `prompts/base.md`（角色/颜色标记/LaTeX 约束，沿用现有格式规则）+ `prompts/<module_id>.md`（每模块分析焦点），保持 `ai.prompt_file` 可覆盖。
- **图文一起解读**：`render_figure` 返回 PNG base64，与文本一起放入 `user_content`（`[{type:"text"},{type:"image_url"}]`）；`_call_provider_internal` 需放开 content 类型。非视觉模型降级为"仅文本 + 图表统计摘要"。
- **数据边界**：工具只暴露 DEG/富集结果表（复用 `deg_limit`/`enrichment_limit` 与 `max_input_tokens` 截断），工具层**拒绝读取表达矩阵路径**——白名单文件清单来自配置，天然满足"不给完整表达矩阵"。
- **兼容性**：`fallback_providers`/`pricing`/`max_input_tokens` 继续生效于每轮调用；无 AI Key 或 `ai.enabled=false` 行为不变（`AI.qmd` include 缺文件时已有容错需确认）。

## 5. 实施步骤（建议 4 个 PR 粒度）

1. **P1 引擎**：`_call_provider_internal` 支持 tools 与 image content；新增 `ai/agent.py` 骨架 + 4 个工具 + 单元测试（mock 客户端）。
2. **P2 提示词**：`prompt.txt` 拆分为 `prompts/` 目录；`consolidate_rna_seq_data.py` 保留为 P0 回退（`ai.agent.enabled: false` 时走旧路径）。
3. **P3 图片**：`render_figure` 工具接入 `omics/rna/analysis` 与 `print_theme`，PNG 缓存到 `data/ai_reports/figures/`；agent 配置增加 `allow_vision`。
4. **P4 回填与文档**：`write_section` 输出按模块拼装 `consolidated_rna_seq_report.md`（结构不变，`AI.qmd` 零改动）；更新 README/Architecture §7。

## 6. 风险与开放问题

- **成本**：逐模块 N 次调用 + 图 token，费用约为现在 N 倍；建议配置 `ai.agent.max_tool_rounds` 与复用同一会话减少重复上下文。
- **视觉模型可用性**：doubao-seed / qwen-vl 支持 image content，但 `fallback` 切到纯文本模型时需自动剥掉图片。
- **确定性**：agent 多轮工具调用引入行为方差，报告可复现性受影响；建议将工具调用轨迹写入 `data/ai_reports/trace.jsonl` 供溯源（与现有 manifests 机制契合）。
- **schema**：`ai` 配置需在 `report.schema.json` 增加 `agent` 子对象校验。
- **开放问题**：PDF 路径的图在渲染期才导出 SVG，agent 若复用 HTML 绘图函数则与 PDF 静态图存在样式差异，是否可接受需产品确认。

## 7. 结论

**可行且改动可控**：引擎层（tools + image content）约 100–200 行；agent 编排与工具约 300–400 行；`AI.qmd` 与回填契约不变。表达矩阵隐私边界已由现有整合器保证，agent 只需沿用白名单工具设计即可延续。
