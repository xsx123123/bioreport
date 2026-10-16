# RNA-seq 封面项目概览面板验证

本次只调整封面元数据展示及其数据组装。原有 Logo、主副标题、品牌落款沿用现有设计。摘要标签保留样本数、分组数；物种、参考基因组、比较组与溯源状态集中进入面板。

## 修改文件

- `templates/pdf/rna-cover.typ.j2`：研究信息／分析溯源双栏，四行对应字段，浅色中央分隔及独立日期行；指定配色、无阴影、自然高度。面板局部取消正文首行缩进，保持多行值左对齐。
- `bioreport/modules.py`：沿用现有 project、report、比较组文件及 provenance 输入；比较组展示名与分析 ID 分离；缺失字段显示“未提供”；过滤示例版本；纠正哈希状态的展示语义。
- `tests/test_rna_pdf_template.py`：更新封面契约，覆盖缺失字段、动态版本、长委托单位及避免虚构校验结果。
- `docs/cover-overview-review.md`：本验证记录。

工作区原先已有未提交修改；本次未撤销这些修改。Git 总 diff 包含此前工作，不能直接视为本次修改清单。

## 实际渲染路径

CLI 配置加载 → provenance 采集 → renderer / compose_report → `rna-cover.typ.j2` → Typst include-before-body → Quarto / Pandoc / Typst → PDF。`templates/_quarto-single.yml.j2` 与生成的 QMD 声明 Typst 格式，`print-style.typ`、`print-body.typ` 提供字体和正文排版。HTML 的 CSS / SCSS 不控制 PDF 封面；无需修改 LaTeX 或 HTML 样式。

## 渲染与检查

使用仓库现有受限环境验证工具运行真实 RNA-seq 数据与全部 21 个 QMD Python 单元，之后由 Quarto `--no-execute` 编译 PDF，没有模拟科学计算或替换数据。输入为 `tests/report.rna.pdf.json`。修改前 PDF 位于 `/tmp/bioreport-cover-before/`，修改后产物位于 `output/cover-overview-review/`。

初始完整渲染命令：

```sh
python tests/render_report_inprocess.py -c tests/report.rna.pdf.json -o output/cover-overview-review --pages
```

后续排版迭代复用已执行 QMD，重新组装封面，再执行 `quarto render qmd/report_pdf.qmd --to typst --no-execute`。最终标准 PDF、布局校验、内容校验和交付清单均已刷新。所有标准输入、哈希、原始配置及执行记录保存在交付目录。

- 标准报告：23 页；完整封面 `cover.png`；实际 PDF `PRJ-RNA-PDF-001_report.pdf`。
- 长文本：`long-text/cover.png` 与 `long-text.pdf`；双行项目主标题、三行中文委托单位、多行版本号保持自然折行、逐行对齐及封面底部署名完整。
- 英文：`english/cover.png` 与 `english.pdf`；英文标题、单位、物种、基因组及流程版本均来自变体配置。
- 缺失可选字段：`missing/cover.png` 与 `missing.pdf`；包括无溯源快照时日期与校验状态的回退，无 None / null / undefined。变体只用于封面压力检查，正文复用标准项目，不能作为独立科研交付。
- 每种变体的实际输入快照：对应目录 `cover-input.json`。
- 中文字体、拉丁学名真斜体、浅色分隔、折行与双栏对齐均已查看实际 PDF 栅格截图。
- A4 灰度打印预览：`cover-print-300dpi.png`。检查打印分辨率栅格与嵌入字体；未使用实体打印机。
- 标准 PDF 校验：`pdf-validation.json`；科学内容校验：`content-validation.json`；交付清单校验：`provenance-validation.json`。
- 封面之外第 2–23 页逐页栅格比较，使用现有视觉比较工具只遮罩运行时生成时间的字形；正文页面像素一致。详细结果与封面嵌入字体检查见 `cover-audit.json`。
- 定向测试：54 passed，1 skipped（需要另行启用的标准 CLI 集成测试）。模板最终排版变更后再次检查：3 passed。

## 数据真实性与边界

项目、委托单位、物种、参考基因组来自现有配置；比较组来自 contrasts CSV，分析仍使用原始 ID `2_vs_1`，封面展示 `Group 2 vs Group 1`；日期来自配置或真实 provenance 生成日期；BioReport 版本来自运行中的包版本。没有添加模板常量项目、日期、物种或校验结论。

示例输入的 pipeline_version 为 `RNAFlow example`，因此封面显示“未提供”，不会猜测真实版本。现有 provenance 的 input_checksums 仅能证明完成指纹计算，不能证明与可信基准完成比对，因此显示“SHA-256 指纹已记录（7 个输入文件）；未比对可信基准”。本次没有修改证据或校验逻辑，也没有引入未经支持的 Verified 状态。

已知限制：现有元数据接口未提供可信哈希基准比对结论；本次不会宣称 SHA-256 Verified。极端无界长度仍受单张 A4 的物理容量限制；验证覆盖本记录所列中英文长文本。实体打印效果尚未验证。
