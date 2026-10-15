# BioReport 开发计划（TODO）

## v3 规划

### AI 管线去 RNA 化：按组学分派的数据整合契约

**现状**：`bioreport/pipeline.py` 中 AI 管线的整合步骤写死 RNA——直接 import
`bioreport.utils.consolidate_rna_seq_data`，且中间文件名硬编码为
`consolidated_rna_seq_data.txt` / `consolidated_rna_seq_report.md`。任何非 RNA
组学包无法复用 AI 解读管线，核心引擎与 RNA 实现存在隐性耦合。

**目标（v3 实现）**：

1. 在组学包契约（`OmicsPackage` / `Registry` 注册接口）上增加
   `consolidate()` 方法，由各组学包提供自己的数据整合器：
   - 输入：解析后的 `input_files`、AI 配置（限额、prompt 等）、输出目录
   - 输出：整合后的文本 + 解读 Markdown 的目标路径约定（纳入契约，不再硬编码文件名）
2. `pipeline.py` 按当前报告选择的 assay 从注册表分派到对应整合器，
   引擎本身不 import 任何组学实现（保持现有 lazy-load 风格）。
3. `templates/shared/AI.qmd` 中的 include 路径改为由组合器按契约注入，
   或约定组学包注册时声明解读产物的 staged 路径。
4. 迁移 `consolidate_rna_seq_data.py` 至 `omics/rna/` 包内，
   `bioreport/utils/` 只保留真正组学无关的工具。

**验收**：新增一个最小非 RNA 组学包即可走通「整合 → 模型解读 → 渲染前就绪」
全流程；RNA 行为与现有输出保持一致（回归 `tests/test_modules.py` 中
AI include 相关用例）。

**暂不处理的原因**：当前仅内置 RNA-seq 模块，硬编码不影响任何现有功能；
先完成共享页迁移与 CLI 身份独立（见 git 历史），契约设计留待 v3 与
多组学模块扩展一并落地。

---

_维护约定：完成事项及时打勾或移除；每项需注明现状、目标与验收方式。_
