<!-- 一个 PR 解决一件事。多件事请拆开。 -->

## 这个 PR 做了什么

<!-- 一两句话，能让 reviewer 不读 diff 也能 get 到。 -->

## 为什么这样做

<!-- 设计动机 / 替代方案 / 取舍。可选。 -->

## 自测清单

- [ ] `uv run pytest -q` 全绿
- [ ] `uv run ruff format --check . && uv run ruff check .` 全绿
- [ ] `npm run build` 全绿
- [ ] 改了 env 变量 → 同步更新了 `server/.env.example` 和 `CONFIG.md`
- [ ] 改了 API → 同步更新了 README 的 API 列表
- [ ] 改了用户可见行为 → 在 `CHANGELOG.md` 的 `[Unreleased]` 加了一行

## 相关 issue

Closes #
