# Changelog

本项目的重要变更记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 变更

- 建立版本校验、CHANGELOG 和 GitHub Actions 发布流程。
- 增加报告运行历史、搜索和 Workspace v1 证据浏览能力（[#6337bec](https://github.com/xsx123123/bioreport/commit/6337bec)）。
- 增加按结果的 AI 解读与 HTML Plotly PNG 导出规范（[#39c5be8](https://github.com/xsx123123/bioreport/commit/39c5be8)、[#d227236](https://github.com/xsx123123/bioreport/commit/d227236)）。
- 完善 PDF 语义布局、字体、封面、报告溯源和项目文档（[#2d5ea98](https://github.com/xsx123123/bioreport/commit/2d5ea98)、[#b4a603a](https://github.com/xsx123123/bioreport/commit/b4a603a)）。

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

[Unreleased]: https://github.com/xsx123123/bioreport/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/xsx123123/bioreport/releases/tag/v2.0.0
