# 本地测试配置

`report.rna.local.json` 用仓库内的 `examples/rna-seq/data/` 作为输入，适合在宿主机直接运行：

```bash
python -m bioreport run \
  -c tests/report.rna.local.json \
  -o output/rna-report
```

`configs/report.example.json` 保留 `/data` 容器挂载路径，适合 Docker；不要在宿主机直接使用它。
