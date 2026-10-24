# 共享模板规范

本目录负责各组学共用的 Quarto 配置、公共页面、视觉样式和资源。组学章节放到 `omics/<name>/qmd/`；完整的创建、注册与验收流程见 [组学模板开发规范](../omics/README.md)。

## 可以直接复用的内容

| 位置 | 作用 | 修改原则 |
| --- | --- | --- |
| `_quarto-single.yml.j2` | 单份报告的 Quarto 项目配置 | 复用；不为每种组学复制一份 |
| `_quarto.yml.j2` | website 布局配置 | 复用；保留公共导航、资源和主题约定 |
| `shared/` | `about`、`faq`、`license`、`trademark`、`provenance`、`ai` 公共模块 | 公共中文页统一维护；不要写入某个组学必需的输入键 |
| `shared/assets/` | 架构图等公共资源 | 更新源文件与对应的离线资源，不混入某个项目的结果图 |
| `theme/` | HTML 主题、明暗模式、导航、表格和资源加载 | 公共样式优先；变更后验证 RNA 与 GWAS |
| `logo/`、`reference/` | 品牌资源、参考文献与引用样式 | 可复用；组学新增引用按页面元数据声明 |
| `pdf/` | Typst 公共打印规则及各组学专属封面 | 按 [PDF 规范](pdf/README.md) 区分共享文件与专属文件 |
| `Taotao/` | 可选桌面宠物资源 | 复用现有配置开关，不作为组学模块依赖 |

公共输出函数不在此目录，QMD 应优先使用：

- [render_output.py](../bioreport/utils/render_output.py)：`show_figure()`、`show_table()`、`show_print_table()` 等公共图表输出函数；按各函数签名传递标题、说明与证据。
- [plotly_style.py](../bioreport/utils/plotly_style.py)：共享交互图样式。
- [print_theme.py](../bioreport/utils/print_theme.py)：静态导出与打印图形样式。
- [report/](../bioreport/report/)：报告语义块、布局和记录。新增组学优先接入现有输出通道。

这些工具可复用不代表所有图形都能自动导出为 PDF。新图型仍需验证静态导出、分页与最终 PDF，必要时编写对应的静态绘图实现。

## 需要手动创建的内容

项目概况、分析流程、质量控制、分析结果、数据读取和专属图表属于组学包。新组学可以参考 RNA/GWAS 的结构，但必须重新核对字段、单位、统计含义、阈值、章节文字和方法引用；不能复制整套 RNA 页面后仅替换标题。

需要双语时手动准备对应的 `en/` 页面，并完成语言路由接入。目前 `shared/` 没有统一的英文页面回退机制：若报告选择公共页，必须保证其英文源在所选组学的内容根目录可解析。已有 RNA 的英文公共页不会随 GWAS 或新组学自动装配。

公共页的组学特例应明确记录用途。例如 RNA 在本包内提供 PDF 版 `about` 与 `provenance`，由组合器显式选择；这不意味着所有组学都应复制这些特例。

## 装配规则：一次只允许一个组学覆盖层

CLI 的装配顺序是：

1. 将本目录复制到临时项目的 `templates/`。
2. 将 `templates/shared/` 复制为临时 `templates/qmd/`。
3. 按配置及 `--omics` 选择结果，将**唯一一个** `omics/<name>/qmd/` 复制到临时 `templates/qmd/`。
4. 组合选定模块，生成 `_quarto.yml`、`qmd/report.qmd` 或 `qmd/report_pdf.qmd`，再交给 Quarto。

不同组学的 `index.qmd`、`results.qmd` 等同名文件可以在各自包内存在，但不得在一次运行中依次复制多个组学包。这正是之前 GWAS 页面覆盖 RNA 页面、触发 `project_summary_file` 错误的原因。混合组学报告目前不受支持。

公共资源与组学资源会在临时目录合并。专属资源采用可辨认的文件名，如 `<name>-workflow.svg`，避免意外覆盖公共资产。需要覆盖共享页面时应明确列出覆盖文件、原因、语言和输出格式，并增加回归检查。

## 不应手工维护的运行产物

临时项目中的 `qmd/report.qmd`、`qmd/report_pdf.qmd`、`qmd/provenance.json`、`qmd/report-plan.json`、`pdf/print-context.typ` 和渲染后的封面由引擎生成。不要通过修改 `output/` 或 `failed-render/` 中的这些文件来实现永久模板变更；应修改对应的源码或组合逻辑。

新增一个公共页面时，除创建 QMD，还需在 [modules.py](../bioreport/modules.py) 的 `MODULES` 中注册，按需设置导航图标，并检查 [安装包声明](../pyproject.toml)。公共 `shared/*.qmd` 目前使用显式文件清单；仅新增文件不会自动进入安装包。组学页面则遵循组学包的 `register(registry)` 流程。
