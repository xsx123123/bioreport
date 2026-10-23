# Changelog

本项目的重要变更记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.2.1] - 2026-10-23

### 修复

- fastp、FastQ Screen、QualiMap、STAR 质控输入路径缺失或未配置时，显示缺失提示并继续生成其余报告内容。
- 统一输入校验、中英文 HTML/PDF 和网站报告的质控跳过逻辑；FastQ Screen 的 R1 或 R2 缺失时跳过整个污染检测子节。
- 在日志、溯源信息和报告清单中记录跳过项，并跳过对应的 AI 解读和 PDF 方法描述。
- 保留核心分析输入及已有路径类型、读取权限的严格校验，补充缺失输入场景的回归测试。

### 变更

- 报告引擎版本调整为 0.2.1。

## [2.0.1] - 2026-10-20

### 新增

- 双语（中文/英文）RNA 报告版本与语言切换。
- 报告运行历史、搜索和 Workspace v1 证据浏览能力（[#6337bec](https://github.com/xsx123123/bioreport/commit/6337bec)）。
- 按结果的 AI 解读与 HTML Plotly PNG 导出规范（[#39c5be8](https://github.com/xsx123123/bioreport/commit/39c5be8)、[#d227236](https://github.com/xsx123123/bioreport/commit/d227236)）。
- 静态 Mermaid 预编译、离线字体、Plotly 运行时本地缓存与共享网站输出，提升离线交付能力和 HTML 加载性能。
- HTML 表格精度控制、表达式表格渲染与报告资源审计能力。

### 变更

- 建立版本校验、CHANGELOG 和 GitHub Actions 发布流程。
- 完善 PDF 语义布局、字体、封面、报告溯源和项目文档（[#2d5ea98](https://github.com/xsx123123/bioreport/commit/2d5ea98)、[#b4a603a](https://github.com/xsx123123/bioreport/commit/b4a603a)）。
- 优化报告主题、导航与交付目录结构。
- 报告引擎版本更新至 2.0.1。

## [2.0.0] - 2026-10-15

这是配置驱动架构的重大版本更新（Beta）。

### 新增

- 配置驱动的报告引擎，统一支持 JSON/YAML 配置、模块编排和自定义 QMD 模块。
- HTML 和 Typst PDF 双格式报告交付，支持交互式图表与离线资源。
- RNA-seq 报告模块，覆盖质控、样本关系、表达、差异表达和富集结果。
- AI 配置接口、报告溯源清单、内置字体、PDF 排版和报告完整性校验能力。
- Docker 部署草稿和可扩展的共享模板目录。

### 变更

- 共享模板和核心引擎从 RNA 专属路径迁移到通用 BioReport 架构。
- 报告文件名统一为 `<project_id>_report.<格式>`，旧版配置仍由配置加载器兼容。

### 移除

- 旧版演示产物和旧布局不再参与当前生成路径，保留内容移入 `archive/`。

## 历史版本

- `v0.0.1`（2026-01-13）：项目初始化与 Quarto 报告原型（[#53d2bf3](https://github.com/xsx123123/bioreport/commit/53d2bf3)）。
- `v0.0.2`（2026-01-14 至 2026-01-15）：RNA-seq 报告、配置更新和 Web/火山图改进。
- 2026-01-27 的 `v0.0.3` 提交未形成 Git tag，因而不作为已发布版本列出。

[Unreleased]: https://github.com/xsx123123/bioreport/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/xsx123123/bioreport/releases/tag/v0.2.1
[2.0.1]: https://github.com/xsx123123/bioreport/releases/tag/v2.0.1
[2.0.0]: https://github.com/xsx123123/bioreport/releases/tag/v2.0.0
