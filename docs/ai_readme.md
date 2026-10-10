# AI 模块说明（归档）

AI 流程已经并入根目录 `bioreport` 包，由统一命令编排：

```bash
bioreport run -c configs/report.example.json -o output
```

AI 参数位于配置文件的 `ai` 节，运行时由 `bioreport.pipeline` 调用
`bioreport.utils.consolidate_rna_seq_data` 的业务函数。供应商、模型、温度和
输入摘要限制都应通过 `configs/*.json` 配置，不再使用独立的 AI CLI、旧配置文件
或旧依赖清单。

当前权威文档是仓库根目录的 [README](../README.md)。
