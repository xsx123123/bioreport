# 组学模板开发与注册规范

本目录保存组学专属的数据契约、分析函数和 QMD 内容。公共页面与视觉样式见 [共享模板规范](../templates/README.md)，PDF 的复用边界见 [PDF 模板规范](../templates/pdf/README.md)。新增组学必须完成本文的注册与验收步骤后才能作为受支持类型发布。

## 1. 目录归属与复用边界

| 内容 | 放置位置 | 新组学如何处理 |
| --- | --- | --- |
| 关于、许可、商标、FAQ、溯源、公共 AI 页面 | `templates/shared/` | 复用公共源，不复制后修改成另一套公共页面；译文及格式专用版本见下文 |
| HTML 主题、导航、字体、离线资源加载 | `templates/theme/`、`bioreport/assets/` | 复用；公共改动需同时验证已有组学 |
| 通用表格、图形输出与打印布局 | `bioreport/utils/`、`bioreport/report/`、`templates/pdf/` | 复用；入口见共享模板规范 |
| 项目概况、分析流程、QC、结果章节 | `omics/<name>/qmd/` | 按本组学数据与分析含义编写；可以参考现有页面结构 |
| 数据读取、计算、统计和组学专属绘图 | `omics/<name>/analysis/` | 按本组学实现，不依赖 `omics/rna/analysis/` 等其他组学包 |
| 模块 ID、输入依赖、父子关系与默认章节 | `omics/<name>/modules.py` | 必须创建并注册 |
| 组学参数契约 | `omics/<name>/schema.json` | 声明本组学参数；文件不会自动接入配置校验 |
| 专属封面及打印差异 | `templates/pdf/<name>-*` | 按需创建，并接入组合器；通用 PDF 不要求专属封面 |
| 示例配置、最小数据与回归测试 | `configs/`、`examples/`、`tests/` | 必须新增，使用可复现的小数据 |

能跨组学使用的工具应放入核心公共层，再由各组学调用。不要通过导入另一个组学包来复用数据解释逻辑。例如 RNA 的 TPM、差异表达阈值、样本分组与 GWAS 的 SNP、性状、关联阈值不能只改标题后沿用。

## 2. 推荐目录结构

以下 `<name>` 是占位符，实际使用稳定的小写 Python 包名，例如 `proteomics`：

```text
omics/<name>/
├── __init__.py               # 导出 register
├── modules.py                # Module 列表与 register(registry)
├── schema.json               # 组学参数契约
├── analysis/
│   ├── __init__.py
│   └── plots.py              # 数据读取与图形生成；按需拆分
└── qmd/
    ├── index.qmd             # 必须有对应的 <name>.index 注册项
    ├── workflow.qmd          # 按实际功能提供
    ├── qc.qmd
    ├── results.qmd
    ├── modules/results/
    │   ├── setup.qmd         # 子章节共享初始化
    │   └── abundance.qmd     # 示例结果子章节
    ├── assets/               # 本组学资源，文件名建议带组学前缀
    ├── pdf/                  # PDF 对应章节与子章节
    │   └── ...
    └── en/                   # 英文对应章节与子章节
        ├── ...
        └── pdf/
            └── ...
```

`stage_omics_templates()` 当前通过注册项 `<name>.index` 的 `package_root` 查找 `qmd/`，所以即使某份配置不选择首页，组学包也必须注册首页。

只支持中文 HTML 时不必先创建所有格式，但必须准确声明支持范围。支持 PDF 或双语时，对应文件与引擎接入都必须完成，不能只创建空目录。

## 3. 页面与数据契约

- `Module.qmd` 是相对组学包根目录的路径，如 `qmd/results.qmd`；`package_root` 指向该包自身目录。
- 数据从 `load_config()` 或 `load_project_metadata()` 读取，使用解析后的 `input_files`，不要写入开发机绝对路径。路径规则见 [配置加载器](../bioreport/config.py)。
- 直接必需的输入键写入 `required_inputs`。缺失时允许整节跳过才设置 `skip_if_missing_inputs=True`；跳过应显示缺失说明，不能伪造数据。
- `optional_inputs` 表示额外可用输入，不能代替对必需输入的声明。复合章节要核对实际子章节的依赖。
- `parent` 与 `setup_qmd` 配套使用；独立选择子模块时，组合器读取父页面元数据并加入初始化。父模块与其子模块不能同时出现在所选列表中。
- 顶层标题由组合器生成，章节正文一般从 `##` 开始。Python chunk label 应全报告唯一，建议带组学和章节前缀，如 `proteomics-abundance-setup`。
- QMD 只负责展示与调用；复杂的数据解析和绘图放到 `analysis/`。图表通过公共输出函数呈现，不能把 `.show()` 当成跨 HTML/PDF 的统一出口。

组合器按语言与输出格式读取不同的文件，**没有自动生成译文或 PDF 页面的功能**：

| 注册路径 | 中文 HTML | 中文 PDF | 英文 HTML | 英文 PDF |
| --- | --- | --- | --- | --- |
| `qmd/index.qmd` | `qmd/index.qmd` | `qmd/pdf/index.qmd` | `qmd/en/index.qmd` | `qmd/en/pdf/index.qmd` |
| `qmd/modules/results/setup.qmd` | 原路径 | `qmd/pdf/modules/results/setup.qmd` | `qmd/en/modules/results/setup.qmd` | `qmd/en/pdf/modules/results/setup.qmd` |

此表描述已接入双语路由后的路径约定；新组学还需完成第 5 节中的语言接入。

组合器首次展开注册页面的 include 时，以当前语言内容根目录（`qmd/` 或 `qmd/en/`）解析路径。HTML 父页面使用 `{{< include modules/results/abundance.qmd >}}`；PDF 父页面使用 `{{< include pdf/modules/results/abundance.qmd >}}`。被包含文件内的嵌套 include 则相对该文件所在目录解析。直接选择子模块与通过父模块 include 子模块时的起点不同，含嵌套 include 的子模块必须分别验证这两种用法。路径不能逃出内容根目录，也不要 include 其他组学的文件。

公共中文页可直接复用 `templates/shared/`。目前公共页没有完整的统一英文目录回退：新组学英文报告若选择 `about`、`provenance` 等页面，需要在本包 `qmd/en/` 提供相应的公共页译文，或先实现并验证共享英文资源装配。不要假定 RNA 包中的英文公共页会一起复制。

## 4. 完成模板后注册模块

以 `proteomics` 为例，下面是首页、结果与结果子模块的最小注册示例；实际项目按支持范围补充流程、QC 等章节及对应输入。

`omics/proteomics/modules.py`：

```python
from pathlib import Path
from bioreport.registry import Module

_ROOT = str(Path(__file__).resolve().parent)
MODULES = [
    Module(
        "proteomics.index", "qmd/index.qmd", "项目概况",
        category="index", package_root=_ROOT,
        required_inputs=("sample_file",), icon="house",
    ),
    Module(
        "proteomics.results", "qmd/results.qmd", "蛋白定量结果",
        category="results", package_root=_ROOT,
        required_inputs=("protein_matrix_file",), icon="bar-chart",
    ),
    Module(
        "proteomics.results.abundance", "qmd/modules/results/abundance.qmd",
        "蛋白丰度", category="results", package_root=_ROOT,
        required_inputs=("protein_matrix_file",),
        parent="proteomics.results",
        setup_qmd="qmd/modules/results/setup.qmd",
    ),
]


def register(registry):
    registry.register_omics(
        "proteomics",
        MODULES,
        defaults=("proteomics.index", "proteomics.results"),
    )
```

`omics/proteomics/__init__.py`：

```python
from .modules import MODULES, register

__all__ = ["MODULES", "register"]
```

[自动发现入口](./__init__.py) 会遍历 `omics` 下的 Python 子包，导入后调用其 `register(registry)`；[注册表](../bioreport/registry.py) 首次加载时触发此过程。不需要再建一份手工 import 清单，也不要在包导入时主动重复调用注册函数。新增包后用新进程验证，已初始化的注册表不会自动热重载。

所有 ID 必须使用自己的前缀，不能注册 `rna.*`、`gwas.*` 或覆盖公共页面 ID。新包不要增加全局 `index`、`qc`、`results` 等通用 alias：当前全局 alias 字典可能被后加载的包覆盖。CLI 已能按所选组学将短名解析到该组学；示例配置优先使用完整 ID。

## 5. 注册后的引擎接入清单

**模块注册成功不代表 CLI、双语、PDF 和安装包已经全部接通。** 当前仍需检查以下位置：

| 接入点 | 需要完成的工作 |
| --- | --- |
| [CLI](../bioreport/cli.py) `build_parser()` | `--omics` 目前只接受 `rna`、`gwas`；新组学需加入 choices，并同步帮助与文档 |
| [组学选择](../bioreport/modules.py) `select_report_omics()` | 扩展 `report.type` 映射；完整注册 ID 已可用于推断，但新类型的默认模块与参数冲突仍需验证 |
| [模板装配](../bioreport/cli.py) `stage_omics_templates()` | 验证 `<name>.index.package_root/qmd` 正确；保持每次只复制所选组学，禁止重新遍历全部包叠加模板 |
| [语言选择](../bioreport/i18n.py) | 若承诺双语，扩展组学识别、`is_bilingual()` 及英文默认标题 |
| [报告组合](../bioreport/modules.py) `compose_report()` | 当前英文内容根目录和专属 PDF 分支显式识别 RNA/GWAS；新增类型需接入英文路由，专属封面/摘要按需接入 |
| [配置校验](../bioreport/config.py) 与 [主 Schema](../bioreport/report.schema.json) | 当前只直接校验主 Schema。`omics/<name>/schema.json` 不会因注册自动加载；新参数需明确接入校验或注明仅为契约文档，并测试非法值 |
| [安装包声明](../pyproject.toml) | 在 `tool.setuptools.package-data` 中加入该包的 QMD、Schema、资源；额外 Python 依赖也需声明 |
| 配置、数据、测试 | 添加真实可运行的示例，证明安装后、子模块独立选择和不同格式均可工作 |

例如在 `tool.setuptools.package-data` 中新增（按真实资源类型调整）：

```toml
"omics.proteomics" = ["qmd/**/*.qmd", "qmd/assets/*.svg", "qmd/assets/*.png", "schema.json"]
```

`templates/pdf/` 下的现有 `*.typ`、`*.typ.j2`、`*.lua` 通配声明会包含同类新文件；新增其他后缀或资源目录时仍需补充打包规则。

## 6. 验收与发布

以下命令以**完成上述接入后的** `proteomics` 包与示例配置为前提，并不表示仓库目前已提供该组学：

```bash
python -c 'from bioreport.registry import get_registry; r = get_registry(); print(r.resolve("proteomics.index")); print(r.qmd_path(r.resolve("proteomics.index")))'
python -m bioreport validate --omics proteomics -c configs/report.proteomics.example.json
python -m bioreport run --omics proteomics -c configs/report.proteomics.example.json -o output/proteomics-check --dry-run
python -m bioreport run --omics proteomics -c configs/report.proteomics.example.json -o output/proteomics-check
```

- [ ] 注册项、默认模块、模板路径与输入键一致；参数与模块前缀冲突时提前报错。
- [ ] 默认模块、独立子模块、共享页均能组装，缺少可跳过输入时出现说明。
- [ ] 临时项目只有所选组学的专属模板，没有 RNA/GWAS 等其他组学的执行代码。
- [ ] 对承诺支持的中文/英文 × HTML/PDF 逐项实际渲染；`validate` 与 `--dry-run` 不执行 QMD 中的数据分析代码，不能代替实际渲染。
- [ ] 如支持 `website`，单独验证页面链接、语言切换与资源路径；该布局不支持 PDF。
- [ ] 核对图表统计含义、单位、阈值与上游结果，不能只检查文件是否生成。
- [ ] 运行相关回归测试，参考 [组学隔离测试](../tests/test_cli_omics.py)、[模块测试](../tests/test_modules.py)、[注册表测试](../tests/test_registry.py)。
- [ ] 构建 wheel/sdist 并检查内容；在独立环境安装后运行示例，确认没有依赖源码目录中的漏打包资源。

不要把尚未实现的占位组学目录放进 `omics/`：自动发现会导入它，可能影响所有现有报告。未完成的设计或代码示例保留在文档中。
