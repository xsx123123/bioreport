# PDF 模板复用与扩展

PDF 的业务内容位于 `omics/<name>/qmd/pdf/`，本目录负责 Typst 版式。英文业务内容位于 `omics/<name>/qmd/en/pdf/`。模块注册和完整接入流程见 [组学开发规范](../../omics/README.md)。

## 共享文件：直接复用

| 文件 | 职责 |
| --- | --- |
| [print-style.typ](print-style.typ) | 公共字体、页眉页脚、章节与图表编号、图表布局等 |
| [print-body.typ](print-body.typ) | 正文开始时恢复统一的字体设置 |
| [print-observations.typ](print-observations.typ) | 公共打印布局观测 |
| [layout.lua](layout.lua) | 公共 Pandoc/Typst 转换规则 |

`print-context.typ` 是组合器在运行时生成的项目、字体和语言上下文，不是需要新增组学手工创建的源模板。公共样式由 [compose_report()](../../bioreport/modules.py) 装入；不要把共享代码复制进每个 `<name>-style.typ`。

## 组学专属文件：按需创建

| 文件模式 | 何时创建 | 内容要求 |
| --- | --- | --- |
| `<name>-cover.typ.j2` | 需要本组学专属中文封面 | 使用本组学项目元数据、统计指标和说明 |
| `<name>-cover.en.typ.j2` | 承诺提供专属英文封面 | 对应的英文标题、字段与文案 |
| `<name>-style.typ` | 公共打印规则无法表达必要差异 | 仅保存差异，不复制公共页眉、表格、分页规则 |

现有 [GWAS 样式](gwas-style.typ) 只有扩展说明，实际采用公共打印规则。新组学没有差异时可直接采用通用 PDF 布局，不必创建一份空样式或专属封面。

创建文件后还必须在 `compose_report()` 中接入模板选择、Jinja 上下文和 `include-in-header`。当前 RNA/GWAS 使用显式分支，新增文件不会自动生效。渲染后的 `<name>-cover.typ` 属于运行产物。

## PDF 内容必须单独核对

- 为支持 PDF 的每个注册页面、子页面和 `setup_qmd` 创建相应的 `qmd/pdf/` 文件；支持英文时补齐 `qmd/en/pdf/`。组合器不会自动从 HTML 版本回退。
- PDF 父页面的 include 使用相对当前语言内容根目录的 `pdf/modules/...` 路径，参考 [GWAS PDF 结果页](../../omics/gwas/qmd/pdf/results.qmd)。
- 按本组学编写项目摘要、方法说明、指标和结果解释。RNA 的 `pdf/summary.qmd` 与方法附录由专属分支加入，不是新组学默认具有的页面。
- HTML 的交互表格、滚动区域和 Plotly 控件不能直接作为 PDF 交付。使用公共打印输出，验证长表、长标签、大图和空结果。
- 表格、图片、标题与证据记录使用公共输出和布局通道；不要在业务 QMD 中重新实现一套全局编号与分页规则。
- 对支持的语言实际生成并检查 PDF。模板组装成功只证明路径和结构可解析，不能证明统计结果、字体与版式正确。

同目录新增的 `*.typ`、`*.typ.j2`、`*.lua` 已被当前 [打包通配规则](../../pyproject.toml) 覆盖；新资源类型需另加声明。修改共享样式时同时检查已有 RNA/GWAS 的 PDF，专属样式不能改变另一组学的输出。
