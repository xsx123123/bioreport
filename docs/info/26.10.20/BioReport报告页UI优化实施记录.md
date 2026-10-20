# BioReport 报告页 UI 优化实施记录

日期：2026-10-20。对应同目录《BioReport报告页UI优化实施手册.md》。当前状态：代码实施与静态检查已推进，尚未完成视觉验收，不能认定手册全部完成。

| 项目 | 修改文件与关键属性 | 证据与剩余工作 |
| --- | --- | --- |
| 1. 语言切换 | `bioreport/i18n.py`、`bioreport/website.py`、`templates/theme/styles.css`：共用分段控件，中文/EN，36px 高、18px 圆角、3px padding；当前段 `aria-pressed=true`、品牌主色白字；单文件切换淡入 200ms | 语言打包和网站控件测试通过；真实点击、键盘与截图仍待 Chromium 验证 |
| 2. 主题按钮 | `templates/theme/report-pages.html`、`styles.css`：36×36px，moon/sun，200ms transform/opacity 动画，中英 tooltip/aria-label，系统初始主题；只在手动操作时保存选择 | 主题运行时视觉检查待执行。现有 Plotly 主题没有跟随页面主题重绘，本次保留该已知限制；DataTables 复用原有亮暗变量 |
| 3. 控件组 | `bioreport/modules.py`、`styles.css`：关于进入主导航末尾；控件间距 8px，校徽额外间距 12px | 七章节/网站十四页面组合测试通过，真实宽度布局待验证 |
| 4. 表格 | `bioreport/utils/html_table.py`、`render_output.py`、`styles.css`：新旧表格路径均有动态右侧渐隐提示；滚动到底撤掉；控件间距 8px；Copy/CSV/Excel 沿用现有动作，改 SVG 图标，32px/6px 圆角；保留导出文件名和列选项 | 表格精度、离线资源和导出配置保留测试通过；实际滚动、搜索、导出和间距仍需浏览器验证 |
| 5. 标题 | `omics/rna/qmd/`、`templates/shared/`：翻译 RNA-seq Result 等混杂标题；中文注释采用全角括号；H1/H2/H3 为 32/24/18px、700/600/600、行高 1.4 | Pandoc 逐一比对 36 个改动标题的旧/新 ID，一致；改变显示文字时显式保留旧锚点。未改变分析代码。全报告视觉通读待执行 |
| 6. 目录 | `report-pages.html`、`styles.css`：本页目录/Contents，展开 Quarto 已生成的小节列表，只显示当前章节，滚动高亮和 2px 品牌色左边框；平滑滚动尊重 reduced-motion；网站页也更新目录 | 路由/history 自动化测试通过；滚动高亮实际效果待验证 |
| 7. 看板娘 | 尚未实施：源码检索未发现组件；现有 `output/theme-ui-verified-20261020` 双语报告的中文 DOM 中也没有 mascot/live2d/waifu 元素 | 已请求用户提供实际报告路径或注入方式。来源未明，未删除角色或灰色 pill，也未添加无法实际控制角色的空配置 |

## 当前验证

- `tests/test_i18n.py`、`test_report_navigation.py`、`test_html_expression_table.py`、`test_report_layout.py`、`test_modules.py`：54 项通过。
- 上述五组加 `test_render_output.py` 的最终联合检查：59 项通过。
- `quarto pandoc` 对改动标题逐一核对：36 个锚点全部保持，记录在 `output/ui-refinement-20261020/anchor-audit.json`。
- 补充单文件外壳的真实控件事件契约检查：点击当前语言或组内空白不切换；非当前语言通过可取消事件交给外壳，保留章节片段，并检查十次往返仅解压两次。语言与路由检查再次通过。
- Python 编译检查和 `git diff --check` 通过。
- 未新增依赖；`i18n.py` 解压、缓存和预加载逻辑未修改。

## 未通过的执行门槛

当前沙箱禁止渲染所需的进程操作：完整 Quarto 执行报 `PermissionError: [Errno 1] Operation not permitted`；Chromium 启动报 `sandbox_host_linux.cc:41 ... Operation not permitted`。未生成修改后的完整报告或截图，1366/2560 × 中英 × 亮暗八种组合不能据此声称通过。

完整渲染命令：

```sh
bioreport run -c output/theme-ui-verified-20261020/run_config_backup.json -o output/ui-refinement-20261020 --db /tmp/bioreport-ui-runs.db
```

已提供 `scripts/verify_report_ui.py`，遍历两种语言、两种主题、两档宽度和每个章节，检查控件状态、尺寸、溢出、表格滚动提示、SVG 按钮和目录文字，并输出改前/改后截图。此脚本尚未获得真实浏览器执行结果：

```sh
python scripts/verify_report_ui.py output/ui-refinement-20261020/X101SC26098749-Z01-J001_report.html --before output/theme-ui-verified-20261020/X101SC26098749-Z01-J001_report.html --output output/ui-refinement-review
```

后续复核：Chromium 仍报相同 `Operation not permitted`；`findmnt -T .git` 明确显示该目录以 `ro` 挂载，限制未解除。

独立 commit 也尚未生成：`git add` 被只读 `.git` 拒绝，错误为 `Unable to create .../.git/index.lock: Read-only file system`。改动保留在工作树，可审阅补丁为 `output/ui-refinement-20261020/report-ui.patch`。

完成浏览器门槛与看板娘来源排查前，目标保持进行中。
