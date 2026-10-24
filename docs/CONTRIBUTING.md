# Contributing to BioReport

## 模板与新组学开发

- [组学模板开发与注册规范](../omics/README.md)：专属文件、数据契约、模块注册、CLI/双语接入、打包与验收清单。
- [共享模板规范](../templates/README.md)：可以复用的页面、样式与输出工具，以及禁止跨组学覆盖的装配规则。
- [PDF 模板规范](../templates/pdf/README.md)：公共打印规则、专属封面与需要手工编写的 PDF 内容。

新增组学完成模板后必须导出 `register(registry)`，并按组学规范完成入口和资源接入；模块自动发现不等于所有输出格式已经可用。

## 提交规范

提交信息使用 Conventional Commits，例如 `feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`chore:` 和 `ci:`。用户可见的 `feat`/`fix` 需要同步更新 [`CHANGELOG.md`](CHANGELOG.md) 的 `Unreleased` 区域。破坏性变更在类型后加 `!`（如 `feat!:`），并在变更记录中写出迁移方式。

## 发布流程

1. 确认 `pyproject.toml` 的版本号与 [`CHANGELOG.md`](CHANGELOG.md) 条目一致。
2. 在主分支提交版本变更，并创建带注释的 `vX.Y.Z` tag。
3. 推送 tag。GitHub Actions 会校验版本、运行非集成测试、构建 wheel/sdist，并创建带附件的 Release。
4. 需要补发已有 tag 时，在 Actions 的 `release` workflow 中手动输入该 tag。

本地可在发布前运行：

```bash
python scripts/validate_release.py
python -m pytest -q tests -k "not integration"
```
