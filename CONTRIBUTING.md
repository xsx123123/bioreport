# Contributing to BioReport

## 提交规范

提交信息使用 Conventional Commits，例如 `feat:`、`fix:`、`docs:`、`refactor:`、`test:`、`chore:` 和 `ci:`。用户可见的 `feat`/`fix` 需要同步更新 `CHANGELOG.md` 的 `Unreleased` 区域。破坏性变更在类型后加 `!`（如 `feat!:`），并在变更记录中写出迁移方式。

## 发布流程

1. 确认 `pyproject.toml` 的版本号与 `CHANGELOG.md` 条目一致。
2. 在主分支提交版本变更，并创建带注释的 `vX.Y.Z` tag。
3. 推送 tag。GitHub Actions 会校验版本、运行非集成测试、构建 wheel/sdist，并创建带附件的 Release。
4. 需要补发已有 tag 时，在 Actions 的 `release` workflow 中手动输入该 tag。

本地可在发布前运行：

```bash
python scripts/validate_release.py
python -m pytest -q tests -k "not integration"
```
