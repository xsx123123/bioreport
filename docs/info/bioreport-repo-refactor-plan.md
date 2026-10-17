# bioreport 仓库优化与多组学扩展方案

> 版本：v1.0（2026-10-10）
> 依据：《仓库架构健康体检》（混乱度 7/10）+ 多组学扩展目标
> 用途：作为搬迁实施的设计依据与验收标准。每一步都可独立验证、独立回滚。

---

## 1. 背景与目标

### 1.1 现状问题（体检结论摘要）

| # | 问题 | 证据 |
|---|------|------|
| 1 | 新旧两套 Python 架构并存 | `bioreport/`（旧，2026-01 后无提交）vs `docker/RNA/rnareport/`（新） |
| 2 | 两套 Quarto 模板 + 脚本副本 | `templates/RNA_Project/` vs `docker/RNA/templates/`，部分文件已分叉 |
| 3 | 入口过多、职责不清 | 8 个可执行文件，`deploy.py` 绕过新流程自行 render |
| 4 | 配置格式与位置混杂 | 3 个 YAML + 2 个旧 `project_summary.json` + 1 个旧 AI `config.yaml` |
| 5 | 源码错误地住在 `docker/` 里 | `docker/RNA/` 实质是完整 Python 项目，Docker 只是交付方式之一 |
| 6 | 无 CI、无打包门禁 | 无 `.github/workflows/`、无 pre-commit；34 个测试默认本地跑 |

### 1.2 优化目标

1. **源码与交付分离**：Python 项目是仓库主体，`deploy/` 只放交付物。
2. **单一代码架构**：删除（或先归档后删除）旧 `bioreport/` 与 `templates/RNA_Project/`。
3. **多组学就绪**：引擎层组学无关；新组学 = 新增 `omics/<x>/` 一个目录 + 注册模块，不改动引擎。
4. **防退化**：Makefile 统一任务入口，CI 做最低限度门禁。

### 1.3 非目标（本期不做）

- 不改动报告的视觉风格（theme 内容原样搬迁）。
- 不改 Quarto 渲染逻辑的行为（renderer 只做路径适配）。
- 不实现"第三方插件式"组学扩展（entry points 插件系统留待确有外部贡献者时再做，见 §9.4）。

---

## 2. 最终目标结构

```
bioreport/                          # 仓库根（建议同时把仓库改名为 bioreport）
├── pyproject.toml                  # 唯一打包入口；包名 bioreport
├── README.md                       # 唯一权威文档（旧 docs/ 收敛进来或删除）
├── Makefile                        # 统一任务入口（§6）
├── .dockerignore
├── .gitignore
│
├── bioreport/                      # 【核心引擎】组学无关，原则上不再因新组学而改动
│   ├── __init__.py                 # 暴露 __version__
│   ├── __main__.py                 # python -m bioreport
│   ├── cli.py                      # 唯一 CLI 入口（子命令：run / validate / init）
│   ├── config.py                   # 配置加载、schema 校验、迁移旧格式
│   ├── registry.py                 # 模块注册表：按组学命名空间聚合（§4）
│   ├── renderer.py                 # 组装临时 Quarto 工程、调用 quarto render
│   ├── modules.py                  # 模块组合逻辑（QMD 拼接、导航生成）——不含任何组学 ID
│   ├── pipeline.py                 # 外部流程编排（AI 数据整合等业务函数调用）
│   ├── report.schema.json          # 引擎层 schema（只校验引擎字段，analysis 放开）
│   └── utils/                      # 引擎通用工具（路径、日志、quarto 探测）
│
├── omics/                          # 【组学模块层】你的"脚本库 + 模板库"，按组学分桶
│   ├── __init__.py                 # 空文件（或 re-export 各组学 register()）
│   ├── base.py                     # OmicsModule 数据类 / 协议定义（供各组学实现）
│   ├── rna/
│   │   ├── __init__.py             # 提供 register(registry) 函数
│   │   ├── modules.py              # rna.* 模块 ID → qmd 路径 + required_inputs + 默认参数
│   │   ├── qmd/                    # 本组学模块模板（从 templates/qmd/modules/ 迁入）
│   │   │   ├── qc/                 # fastp.qmd、star.qmd、qualimap.qmd、screen.qmd
│   │   │   └── results/            # samples.qmd、matrix.qmd、heatmap.qmd、deg.qmd、enrichment.qmd
│   │   ├── analysis/               # 本组学分析脚本（deg.py、pca.py、enrichment.py……）
│   │   │   └── __init__.py
│   │   └── schema.json             # rna 组学自己的 analysis 参数 schema
│   │
│   ├── atac/                       # 预留：新组学照抄 rna/ 结构即可
│   └── .../                        # protein/、metabolome/、singlecell/……
│
├── templates/                      # 【前端样式层】组学无关，所有报告共用
│   ├── _quarto-single.yml.j2       # 单页配置
│   ├── _quarto-website.yml.j2      # 多页 website 配置
│   ├── qmd/
│   │   ├── index.qmd               # 报告首页（通用）
│   │   ├── about.qmd               # 关于页（通用）
│   │   └── partials/               # 可被组学 qmd include 的通用片段（图例、免责声明等）
│   ├── theme/                      # scss/css/js 前端样式库
│   ├── logo/
│   └── reference/                  # bib、csl
│
├── configs/
│   ├── report.example.json         # 主推示例（RNA-seq 完整版）
│   ├── report.no_ai.json           # 精简示例
│   └── report.generic.json         # 跨组学最小示例（来自 examples/generic-assay）
│
├── examples/
│   ├── rna-seq/                    # RNA 示例数据 + report.json
│   └── generic-assay/              # 现有自定义 QMD 示例迁入
│
├── tests/
│   ├── test_config.py
│   ├── test_registry.py            # 新增：模块注册表行为
│   ├── test_modules.py             # 现有 4 个测试迁入并按新路径适配
│   ├── test_render_output.py
│   ├── test_ai_pipeline.py
│   └── test_integration_render.py  # 端到端，默认 skip
│
└── deploy/                         # 【交付层】只放"怎么打包出去"，禁止放源码
    ├── Dockerfile                  # 唯一一份，build context = 仓库根
    └── docker-compose.yml          # 可选：本地挂载数据跑报告的便捷方式
```

### 2.1 每层"不允许出现什么"

| 层 | 禁止 |
|----|------|
| `bioreport/`（引擎） | 任何组学名称、任何具体图表脚本、任何硬编码数据路径 |
| `omics/<x>/` | import 其他 `omics/<y>/` 的内部实现（只允许 import `bioreport.*`） |
| `templates/` | Python 业务逻辑（只允许 Quarto/Jinja/CSS/JS） |
| `deploy/` | Python 源码、模板、测试（只允许 Dockerfile、compose、部署脚本） |
| 仓库根 | 结果 JSON、AI 日志、输出目录（一律进 `.gitignore`） |

---

## 3. 三层架构与依赖规则

```
┌─────────────────────────────────────────────┐
│  组学模块层  omics/rna  omics/atac  ...      │  ← 横向扩展：新组学加目录
│  （qmd 模板 + analysis 脚本 + 模块注册）       │
└───────────────▲─────────────────────────────┘
                │ 只允许向上依赖
┌───────────────┴─────────────────────────────┐
│  核心引擎层  bioreport/                      │  ← 组学无关，长期稳定
│  cli / config / registry / renderer         │
└───────────────▲─────────────────────────────┘
                │ 单向引用
┌───────────────┴─────────────────────────────┐
│  前端样式层  templates/theme  partials       │  ← 纵向复用：所有组学共用
└─────────────────────────────────────────────┘
```

**依赖方向唯一：组学 → 引擎 → 样式。** 反向依赖（引擎认识某个组学、组学之间互调）一律禁止，CI 中可用一条 import-linter（或简单 grep 检查）守住。

---

## 4. 模块注册协议（registry.py 设计）

### 4.1 模块 ID 命名空间

模块 ID 采用 `组学.类别.名称` 三级命名：

```
rna.qc.fastp
rna.qc.star
rna.results.deg
rna.results.enrichment
atac.qc            # 类别可省略一层
generic.finding    # 自定义外部模块仍走 module_definitions，见 4.4
```

规则：
- 引擎自带的通用页不带组学前缀：`index`、`about`。
- 组学前缀必须与 `omics/` 下目录名一致，注册时自动校验。

### 4.2 模块定义结构

每个模块是一个声明式记录（放在各组学的 `modules.py`）：

```python
# omics/rna/modules.py
from bioreport.registry import Module

MODULES = [
    Module(
        id="rna.qc.fastp",
        qmd="qmd/qc/fastp.qmd",        # 相对本组学目录
        title="测序质量评估 (fastp)",
        category="qc",
        required_inputs=["fastp_json"],  # 声明输入键，引擎据此做存在性检查
        default_params={"min_quality": 20},
    ),
    Module(
        id="rna.results.deg",
        qmd="qmd/results/deg.qmd",
        title="差异表达分析",
        category="results",
        required_inputs=["deg_table"],
        default_params={"log2fc_threshold": 1.0, "pvalue_threshold": 0.05},
    ),
    # ...
]
```

### 4.3 注册表接口

```python
# bioreport/registry.py
class Registry:
    def register_omics(self, prefix: str, modules: list[Module]) -> None:
        """组学包启动时调用；校验 ID 前缀、qmd 文件存在、输入键命名合法。"""

    def resolve(self, module_id: str) -> Module: ...
    def validate_inputs(self, module_ids: list[str], available_inputs: set[str]) -> list[str]:
        """返回缺失输入的错误列表，供 cli --dry-run 与 validate 子命令使用。"""

    def qmd_path(self, module: Module) -> Path:
        """定位 qmd：内置模块 → omics/<x>/qmd/...；外部模块 → 相对 JSON 所在目录。"""

_REGISTRY = Registry()

def get_registry() -> Registry:
    if not _REGISTRY.loaded:
        import omics  # noqa: 触发各组学 register()
        _REGISTRY.loaded = True
    return _REGISTRY
```

`omics/__init__.py` 负责按目录自动发现并调用各组学的 `register()`，**新增组学不需要改引擎任何一行**：

```python
# omics/__init__.py
import importlib, pkgutil
from bioreport.registry import get_registry

def load_all():
    reg = get_registry.__wrapped__() if False else None  # 伪代码，实际直接操作内部单例
    for m in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "register"):
            mod.register(get_registry())

def register(reg):
    load_all()
```

### 4.4 外部自定义模块（保留现有能力）

用户在 JSON 里通过 `module_definitions` 注册的外部 QMD 依然支持，且与内置命名空间隔离（要求外部 ID 不得含已注册组学前缀，避免劫持内置模块）：

```json
{
  "report": {
    "modules": ["index", "rna.qc.fastp", "custom.finding", "about"],
    "module_definitions": {
      "custom.finding": {
        "path": "modules/finding.qmd",
        "title": "实验结果",
        "params": {"input_key": "measurements"},
        "required_inputs": ["measurements"]
      }
    }
  }
}
```

### 4.5 analysis 参数的作用域

- 引擎 schema 中 `analysis` 允许任意键（`additionalProperties: true`）。
- 各组学的 `omics/<x>/schema.json` 定义自己的合法键（如 `analysis.rna.deg.log2fc_threshold`）。
- 校验流程：引擎校验结构 → 按已启用组学逐个校验组学参数。未启用组学的参数报错提示"是否缺少模块"。

---

## 5. 打包（pyproject.toml 要点）

```toml
[project]
name = "bioreport"
version = "2.0.0"
description = "Multi-omics report generator (Quarto-based)"
dependencies = [ ... 引擎最小依赖 ... ]

[project.optional-dependencies]
rna = ["pandas", "plotly", "scipy", ...]        # 按需安装：pip install 'bioreport[rna]'
ai  = [ ... AI 依赖 ... ]
dev = ["pytest", ...]

[project.scripts]
bioreport = "bioreport.cli:main"

[tool.setuptools.packages.find]
include = ["bioreport*", "omics*"]

[tool.setuptools.package-data]
"bioreport" = ["report.schema.json"]
"omics.rna" = ["qmd/**/*.qmd", "schema.json"]
"omics.atac" = ["qmd/**/*.qmd", "schema.json"]

[tool.setuptools.data-files]   # 非包资源：样式库与配置示例
# 或更稳妥地：模板/theme 也整体收进包内（推荐），安装后通过
# importlib.resources 访问，保证 pip 安装 / Docker / 本地开发三场景路径一致
```

**关键决定：模板与样式库作为包数据打进 wheel。**
当前 `renderer.py` 用相对仓库的路径找 `templates/`，pip 安装后仓库不在场会失败。搬迁时统一改为 `importlib.resources.files()` 定位（Python ≥ 3.9 写法），本地开发因为 editable install 同样成立。

---

## 6. Makefile（统一任务入口）

```makefile
.PHONY: install install-dev test test-integration dry-run report validate docker-build docker-run clean lint-imports

PYTEST := python -m pytest -q

install:            ## 最小安装
	pip install -e .

install-dev:        ## 开发安装（含 rna 组学与测试依赖）
	pip install -e '.[rna,ai,dev]'

test:               ## 单元测试（当前：40 passed）
	$(PYTEST) tests -k "not integration"

test-integration:   ## 端到端渲染测试（需要 quarto + jupyter + kaleido）
	RUN_REPORT_INTEGRATION=1 $(PYTEST) tests/test_integration_render.py

validate:           ## 校验配置（CONFIG=configs/report.example.json）
	bioreport validate -c $(CONFIG)

dry-run:            ## 试跑不渲染（CONFIG=configs/report.example.json OUT=output）
	bioreport run -c $(CONFIG) -o $(OUT) --dry-run

report:             ## 正式生成（CONFIG=... OUT=...）
	bioreport run -c $(CONFIG) -o $(OUT)

lint-imports:       ## 依赖方向检查（组学之间禁止互相 import）
	! grep -rE "from omics\.(rna|atac|[^.]+)\..* import" omics --include='*.py' \
	  | grep -v "^omics/\1/"   # 实现可用 import-linter 替代

docker-build:       ## 构建交付镜像（build context = 仓库根）
	docker build -f deploy/Dockerfile -t bioreport:latest .

docker-run:         ## 容器跑报告（CONFIG 相对当前目录）
	docker run --rm \
	  -v $$(pwd)/$$(dir $(CONFIG)):/data:ro \
	  -v $$(pwd)/$(OUT):/workspace \
	  bioreport:latest -c /data/$$(notdir $(CONFIG)) -o /workspace

clean:
	rm -rf output _deploy_temp dist *.egg-info
```

## 7. deploy/Dockerfile（唯一交付定义）

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
# quarto + jupyter + kaleido 等系统依赖（按现有 docker/RNA/Dockerfile 原样迁移，
# 仅调整 COPY 路径，因为 build context 变为仓库根）
RUN apt-get update && apt-get install -y --no-install-recommends \
      pandoc curl ca-certificates && rm -rf /var/lib/apt/lists/*
# ... 安装 quarto 的步骤与原 Dockerfile 保持一致 ...

WORKDIR /app
COPY pyproject.toml README.md ./
COPY bioreport/ ./bioreport/
COPY omics/ ./omics/
# templates/ 已作为包数据包含在 bioreport/omics 内，无需单独 COPY；
# 若选择 data-files 方案，则此处 COPY templates/ ./templates/

RUN pip install --no-cache-dir -e '.[rna,ai]'

ENTRYPOINT ["bioreport", "run"]
# 用法：
#   docker run --rm -v /data:/data:ro -v /out:/workspace img -c /data/report.json -o /workspace
```

构建命令固定为（`-f` 与 context 分离，最常见的报错来源）：

```bash
docker build -f deploy/Dockerfile -t bioreport:latest .
```

---

## 8. 迁移路线图（按 PR 切分，每步可验证可回滚）

> 前置：当前工作区有大量未提交修改，**先 commit/stash**，从干净状态切 `refactor/repo-layout`。

### Phase 0 — 冻结与基线（0.5 天）

- [ ] 提交或暂存所有未提交改动（由调用方决定提交边界）
- [x] 记录回归基线：`pytest -q` → 40 passed, 2 skipped（集成测试默认 skip）
- [x] 全仓搜索 `docker/RNA` 字符串（运行代码与文档已收敛；计划文档保留迁移记录）

**验收**：当前工作区仍由调用方控制提交；基线测试结果已记录。

### Phase 1 — 物理搬迁，不改逻辑（1 天）

- [x] `git mv docker/RNA/rnareport ./bioreport`（保留 git 历史）
- [x] `git mv docker/RNA/templates ./templates`；`git mv docker/RNA/configs ./configs`；`git mv docker/RNA/tests ./tests`；`git mv docker/RNA/examples ./examples`
- [x] `git mv docker/RNA/pyproject.toml ./pyproject.toml`
- [x] `mkdir omics && git mv bioreport/plots omics/rna/analysis`（plots 脚本本质是 rna 组学的）；`git mv templates/qmd/modules omics/rna/qmd`
- [x] 引擎内路径适配：CLI 使用 `importlib.resources` + 安装资源；内置 RNA 模块使用 `rna.` 前缀并保留旧别名
- [x] 根目录新增 `.dockerignore`；更新 `.gitignore` 排除结果 JSON / AI 日志 / output/

**验收**：`python -m bioreport run -c configs/report.example.json -o output --dry-run` 通过；`pytest -q tests` 为 40 passed、2 skipped。

### Phase 2 — 打包与注册表（1 天）

- [x] 重写 `pyproject.toml`（§5）：包名 `bioreport`，console script，package-data 收模板
- [x] 新建 `bioreport/registry.py` 与 `omics/base.py`（§4.2/4.3）
- [x] 各组学 `modules.py` 从引擎中拆出（`rna` 先迁）
- [x] `omics/__init__.py` 自动发现注册（§4.3）
- [x] engine schema：`analysis` 放开 `additionalProperties`；`omics/rna/schema.json` 建立
- [x] CLI 增加子命令骨架：`bioreport run|validate|init`

**验收**：editable 安装后的 `bioreport validate`、wheel 安装后的 `bioreport validate`、`make test` 和 `make dry-run` 均通过；核心 CLI 导入不要求 RNA/AI 可选依赖。

### Phase 3 — 交付层与入口统一（0.5 天）

- [x] 新建 `deploy/`，`git mv docker/RNA/Dockerfile deploy/Dockerfile`，按 §7 调整 COPY 路径
- [x] 写 `Makefile`（§6）
- [ ] `make docker-build` 成功；用 `examples/` 数据在容器内渲染出 HTML+PDF（当前环境 Docker socket、Podman/Buildah runtime 均不可用）
- [x] 未新增 `bioreport deploy`；README 已标注部署仅支持 docker-run 方式
- [x] 删除 `docker/RNA/docker_build/`（废弃）、根目录 `package.json`（无用途）

**验收**：容器内渲染产物与本地渲染产物一致（diff HTML 结构或人工抽查）。

### Phase 4 — 清理遗留（0.5 天，单独 PR）

- [x] 旧 `bioreport` 与旧模板已移出仓库到 `/tmp/bioreport-legacy-archive-*`，运行代码零引用
- [x] 删除仓库内旧示例配置：`configs/*.yaml`、根级旧 requirements；加载器仍保留旧 YAML/`project_summary.json` 迁移兼容
  - 例外：保留一个旧格式迁移测试（`project_summary.json` → 新 JSON 的转换测试），确认无用户后再删
- [x] 删除 `bioreport/deploy.py`（硬编码服务器的旧部署脚本，属安全隐患）
- [x] `docs/README.md` 已标记 archived；README 已更新为唯一当前入口

**验收**：运行代码与当前文档已无 `bioreport.core`、`bioreport.loader`、`RNA_Project` 引用；`project_summary` 仅保留在兼容迁移代码和迁移测试中。

### Phase 5 — CI 门禁（0.5 天）

状态：已新增 `.github/workflows/ci.yml`；本地测试、validate、dry-run、wheel 安装和安装后 dry-run 均通过，GitHub hosted runner 的绿灯状态需在远端执行后确认。

最小 GitHub Actions（push / PR 触发）：

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install -e '.[rna,dev]'
- run: pytest -q tests -k "not integration"
- run: bioreport validate -c configs/report.example.json
- run: bioreport run -c configs/report.example.json -o /tmp/out --dry-run
- run: docker build -f deploy/Dockerfile -t bioreport:ci .
```

有条件再加一条 self-hosted runner 跑 `RUN_REPORT_INTEGRATION=1` 端到端。

**验收**：CI 在 main 分支绿灯；故意改坏一个 import 方向能被抓到（lint-imports）。

---

## 9. 长期治理规则（防退化）

### 9.1 新增一种组学的标准动作（checklist）

1. `mkdir omics/<x>`，复制 `omics/rna/` 目录结构
2. 写 `omics/<x>/modules.py` 注册 `x.*` 模块（含 `required_inputs` 声明）
3. 写 `omics/<x>/schema.json` 定义 `analysis` 参数
4. 在 `pyproject.toml` 增加 `[project.optional-dependencies] <x> = [...]`
5. 在 `configs/report.example.json` 增补示例（或新建 `configs/report.<x>.json`）
6. 测试：新增 `tests/test_<x>_modules.py`

**全程不触碰 `bioreport/`（引擎）任何文件。** 如果做新组学时觉得"必须改引擎"，说明引擎抽象缺口子——先停下来讨论，把能力补进引擎再动组学。

### 9.2 每月例行自检（5 分钟）

```bash
make test && make lint-imports && make dry-run
```

### 9.3 文档单一来源

README 是唯一权威文档。其他 `docs/*.md` 要么是 README 的生成产物，要么标注 "Archived (legacy)"。

### 9.4 未来演进（本期不做）

- **entry points 插件**：若将来允许外部仓库贡献组学模块，`omics/` 自动发现可升级为 `importlib.metadata.entry_points(group="bioreport.omics")`，引擎依然零改动。
- **deploy 子命令**：`bioreport deploy` 统一本地/远程部署，替代一切手写 rsync 脚本。
- **theme 版本化**：theme 重大改版时保留 `theme/v1/`、`theme/v2/`，JSON 中按版本引用，避免旧报告无法复现。

---

## 10. 验收总清单

| 项 | 标准 |
|---|---|
| 入口唯一性 | `pip install -e .` 后只有 `bioreport` 一个命令；仓库内可执行 Python 文件 ≤ 4 个（cli/registry/renderer/pipeline） |
| 测试 | `make test` 全绿（当前 40 passed，2 个 integration 默认跳过） |
| 路径三场景一致 | pip 安装 / editable / Docker 内，`bioreport run` 均能定位模板 |
| 镜像 | `make docker-build` 成功且容器内可渲染示例报告 |
| 遗留清零 | `bioreport.core`、`templates/RNA_Project`、旧 YAML、`deploy.py` 均不存在（迁移测试除外） |
| 组学扩展 | 新增一个假组学 `omics/foo/`（照抄结构）不改引擎即可被 `--dry-run` 识别 |
| CI | main 分支绿灯，包含测试 + dry-run + docker build |
