# Docker 与 PDF 部署说明（草案）

> 镜像固定使用 Quarto 1.8.26 Linux amd64 安装包，构建时下载并校验 SHA-256；镜像包含 Chromium、中文字体及 RNA / AI / PDF Python 依赖。构建期间执行 RNA HTML/PDF 冒烟检查。

## Docker 生成报告

### 1. 构建镜像

在仓库根目录执行：

```bash
docker build --platform linux/amd64 -f deploy/Dockerfile -t bioreport:latest .
```

### 2. 准备配置

镜像入口为 `bioreport`，因此生成报告需要显式写 `run`，也可直接使用 `validate` 或 `--help`。构建需要 apt / pip 网络，并需要访问 GitHub 下载固定版本的 Quarto 安装包。

构建保存 Python 版本清单到 `/opt/bioreport-python-packages.txt`。依赖尚未全部锁定，重新构建可能解析到不同版本；建议复用验证后的镜像或 digest。

项目提供以下配置示例：

| 配置文件 | 说明 |
| :--- | :--- |
| `configs/report.example.json` | 完整版 RNA 报告配置，使用容器内 `/data` |
| `configs/report.generic.json` | 通用 assay 示例，使用仓库内示例数据 |
| `tests/report.rna.local.json` | 本地 RNA 示例，使用仓库内示例数据 |

复制配置后，根据实际项目修改 `project` 与 `input_files`。容器内路径必须与挂载点一致。

### 3. 运行报告

请根据实际路径调整 `-v` 挂载：

```bash
# 完整版 RNA 报告
docker run --rm \
  -v /你的/本地/数据目录:/data:ro \
  -v /你的/本地/输出目录:/workspace \
  -v "$(pwd)/configs/report.example.json:/app/configs/report.example.json:ro" \
  bioreport:latest run -c /app/configs/report.example.json -o /workspace

# 通用 assay 报告
docker run --rm \
  -v "$(pwd)/examples/generic-assay:/app/examples/generic-assay:ro" \
  -v "$(pwd)/configs:/app/configs:ro" \
  -v /你的/本地/输出目录:/workspace \
  bioreport:latest run -c /app/configs/report.generic.json -o /workspace
```

`report.layout: single` 生成单文件 HTML；按需设置 `report.output_format` 为 `"html"`、`"pdf"` 或 `["html", "pdf"]`。`website` 布局生成多页 HTML，不能与 PDF 同时使用。报告文件名以 `project.project_id` 为前缀，形如 `<project_id>_report.html` 或 `<project_id>_report.pdf`。

### 4. 干运行

`--dry-run` 会检查配置、模块组合和输入文件，但不会调用 AI 或执行 Quarto：

```bash
docker run --rm \
  -v /你的/本地/数据目录:/data:ro \
  -v "$(pwd)/configs/report.example.json:/app/configs/report.example.json:ro" \
  bioreport:latest run -c /app/configs/report.example.json -o /workspace --dry-run
```

可添加 `--user "$(id -u):$(id -g)"` 让输出归当前用户所有，宿主输出目录必须可写。镜像提供可写临时 HOME，支持任意 UID。项目数据、`.env` 和本地凭证目录已从构建上下文排除。

构建后可独立重跑完整冒烟检查（包括 Kaleido 静态导出、RNA HTML/PDF 和交付校验）：

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  --entrypoint python bioreport:latest /opt/bioreport-smoke-test.py
```

## RNA-seq PDF 模板

RNA-seq PDF 使用独立正文和 Typst 打印排版，包含封面、目录、项目和样本信息、分析流程、质控、表达、差异分析、富集、溯源和交付说明。章节仍由 `report.modules` 控制：

```bash
bioreport run -c tests/report.rna.pdf.json -o output/rna-pdf-report
```

模板职责如下：

- `omics/rna/qmd/pdf/`：PDF 专用章节、图表顺序和精简说明。
- `templates/pdf/print-style.typ`：A4 排版、字号、页眉页码、图块和跨页表格；`rna-style.typ` 提供 RNA 专用覆盖。
- `templates/pdf/rna-cover.typ.j2`：封面 Logo、标题和项目元数据布局。
- `bioreport/modules.py`：根据配置填充封面并组合章节。
- `omics/rna/analysis/`：HTML 与 PDF 共用的数据处理和绘图函数。

PDF 表格提供结果预览，完整结果文件仍保存在配置的数据交付目录中。表达矩阵默认展示前 8 个基因和最多 6 个样本列，差异基因和富集结果默认展示前 10 行。PDF 使用 A4 页面、独立封面和目录、页眉页码及静态 SVG 图表；建议安装 Noto CJK 字体以获得一致的中文排版。

可通过 `report.pdf` 配置表格预览行数、富集 Top N 和 `qc_detail: key / all`。共享样式、验证命令和兼容边界见 [`../docs/info/pdf-style.md`](../docs/info/pdf-style.md)。

启用 `ai.scope: results` 时，PDF 使用两阶段流程：第一次渲染生成图表、表格和结果块清单；随后将每个结果的结构化证据与可用图像提交给模型；最后写入 Markdown 解读卡片并重新渲染 PDF，使卡片出现在对应结果下方。图像无法准备时回退到结构化证据，最终 PDF 仍会执行版式和内容校验。
