# BioReport AI 解读说明

[返回中文 README](README.zh-CN.md) · [English README](../README.md)

本文档记录当前 AI 解读配置、逐结果流程和实现边界。主 README 只保留配置兼容性和后续规划概览。

## 配置

AI 设置位于统一 JSON/YAML 配置的 `ai` 节，当前配置结构已经为 OpenAI-compatible 服务商、逐结果卡片和 PDF 视觉流程预留兼容字段：

| 字段 | 说明 |
| :--- | :--- |
| `enabled` | 是否启用 AI 解读 |
| `model` / `provider` | 模型与服务商；`volcengine`、`aliyun` 提供默认地址和 Key 环境变量，也可使用 `openai-compatible` 配合自定义地址 |
| `base_url` / `api_key_env` | OpenAI-compatible API 地址和 API Key 环境变量名 |
| `temperature` | 模型温度 |
| `max_output_tokens` | 单次输出上限；结果卡片建议设置为 `600`–`1200` |
| `scope` | `results` 为逐结果卡片；`global` 为旧式合并章节 |
| `result_rows` | 每个结果提交给模型的 CSV 行数上限 |
| `prompt_file` | 自定义 Prompt 文件路径 |
| `deg_limit` / `enrichment_limit` | 提交给 AI 的差异基因与通路数量 |
| `vision` / `max_image_bytes` | 视觉输入开关与单张附件上限 |

通用兼容网关示例：

```json
{
  "ai": {
    "enabled": true,
    "provider": "openai-compatible",
    "base_url": "https://llm.example.com/v1",
    "api_key_env": "MY_LLM_API_KEY",
    "model": "provider-model-id",
    "scope": "results"
  }
}
```

所有服务商统一使用 OpenAI Python SDK 的 Chat Completions 接口。默认 Key 环境变量为 `ARK_API_KEY`（`volcengine`）、`DASHSCOPE_API_KEY`（`aliyun`）和 `OPENAI_API_KEY`（`openai` / `openai-compatible`）。引擎还支持 `fallback_providers`、`max_input_tokens` 和 `pricing` 等扩展设置。

## 当前流程

启用 AI 后，默认对 fastp、FastQ Screen、QualiMap、STAR、PCA、表达分布、TPM 矩阵、热图、DEG 和富集结果分别生成解读卡片。HTML 路径在 Quarto 渲染前准备卡片；PDF 的 `scope: results` 使用两阶段流程：

1. 首次 Quarto 渲染生成 PDF 图表、表格和结果块清单。
2. 系统按结果 ID 绑定结构化证据和已渲染图像，对每个结果单独请求模型。
3. 将 Markdown 卡片写入临时数据目录，二次渲染后回填到对应结果下方。

图像无法准备时会回退到结构化证据。当前框架包含结果 ID、输入来源映射、OpenAI SDK 兼容、重试、输入截断、视觉降级和空响应回退。

## 后续计划

当前提示词和解读逻辑仍属于过渡实现。下一版本重点是按 fastp/QC、样本关系、DEG、富集和图表视觉解读拆分专家 Prompt，并统一输出“观察、统计依据、生物学解释、限制条件、建议复核项”。同时增加数值引用、证据一致性、结果为空校验、Prompt 版本、模型参数、evidence hash 和响应状态记录。

后续 AI Agent 将拆分为证据适配、Prompt 注册、模型调用、输出验证和渲染回填等可替换层；Web Workspace v2 计划提供异步解读、证据定位、重新解读、版本保留和 HTML/PDF 原位回填。实施骨架见 [`../todo.md`](../todo.md) 的“AI 逐结果解读 Agent 框架”和“Web 工作台大版本升级：BioReport Workspace v2”。
