# 日志说明

## 当前实现

报告命令的日志由 `bioreport/cli.py` 的 `setup_logging` 统一配置：

- 控制台日志使用 Loguru，输出时间、级别和消息；Rich 用于帮助页与输入文件清单。
- 文件日志写入输出目录下的 `<project_id>_<time>_bioreport.log`（如 `PRJ-2026-001_20261016-143005_bioreport.log`），级别为 `DEBUG`；文件名由 `bioreport/config.py::run_log_name` 以项目标识和运行时间生成。
- 报告交付文件名同理以 `<project_id>_report.<format>` 命名，由 `bioreport/config.py::report_artifact_name` 生成。
- AI 流程和组学分析模块通过 Loguru 复用 CLI 配置，不再维护独立的日志入口。

## 后续扩展位置

如果需要增加 JSON 日志、Trace ID 或按配置调整日志级别，应在以下位置扩展：

1. 在报告配置 schema 中增加 `logging` 配置项。
2. 在 `bioreport/cli.py::setup_logging` 中读取并应用配置。
3. 在 `bioreport/pipeline.py` 和 `bioreport/ai/engine.py` 中传递上下文，不新增独立 CLI 或日志配置文件。

这样可以保持 `bioreport` 单一入口，并让所有报告类型共享同一套日志行为。
