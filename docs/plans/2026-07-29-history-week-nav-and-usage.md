# 2026-07-29 历史页周导航与用量收敛

## 背景

1. 筛选某 UP 后「删除筛选结果」，facets 中该 UP 消失，`SearchableSelect` 回落显示「全部 UP 主」，但 `selectedAuthor` 仍在 → 空列表假象。
2. 「删除全部已结束记录」文案偏实现细节。
3. 多周手风琴列表纵向冗长；希望全局扫密度 + 单周详情。
4. 统计页信息过重；只保留 API 余额与 tokens，迁入历史页。

## 已确认决策

- 删光某筛选后：自动清除无效 author/tag 并重载全量；Select 永不在有 value 时显示「全部」。
- 批量删除菜单：无筛选 `清理历史…`，有筛选 `删除筛选结果…`。
- 周导航：可点击周柱/大方块（非日热力主导航）+ 左右切换 + 下方只展示当前一周。
- 搜索关键词时保持扁平列表。
- 统计页整页移除；历史页紧凑展示余额 + 总/入/出 tokens；费用趋势与 by_operation 不展示。
- 后端 `GET /v1/stats/costs` 保留。

## 步骤

- [x] 1. 修幽灵筛选：`SearchableSelect` 孤儿值展示；`handleBulkDelete` / facets 同步后清无效筛选；空态引导清除筛选
- [x] 2. 批量删除文案与确认标题
- [x] 3. 新增 `WeekNavigator`，历史页单周详情替换多周手风琴；restore 改为 `selectedWeek`
- [x] 4. 历史页嵌入用量条；删除 `StatsPage` 与所有 `/stats` 入口
- [x] 5. 删除未引用的 `Heatmap` / `WeekBars` / 死类型（若无引用）
- [x] 6. 类型检查与构建验证

## 非目标

- 不改 bulk-delete 服务端契约
- 不展示费用趋势 / 本周消费 / 按操作类型
- 不 commit / push

## 验收

1. 筛 UP → 删光 → 回到有效全量或明确清除筛选，不出现「全部 + 空数据」
2. 菜单文案符合决策
3. 周导航全局扫 + 单周列表；搜索扁平
4. 无统计页；历史页可见余额与 tokens
5. 单删、筛选、周总结、返回恢复仍可用

## Implementation notes

- `SearchableSelect` shows orphan values (with `#` for tags) instead of placeholder; dropdown keeps orphan as selected.
- `handleBulkDelete` reloads facets first; clears orphan author/tag only when facets load successfully; filter-clear triggers list reload via `historyFilters` effect; toast mentions cleared filters.
- Empty filtered state: 「没有匹配的记录」+「清除筛选」button.
- Bulk copy: menu `清理历史…` / `删除筛选结果…`; confirm no-filter title uses `历史记录` (not `已结束记录`).
- New `WeekNavigator` + single selected week body; prev/next among `weekGroups` (desc order: ‹ older, › newer).
- Restore key bumped to `biri-youyaku.history.restore.v2` with `selectedWeek`.
- `UsageStrip` under history header: balance + all_recorded tokens; soft-fail.
- Removed StatsPage route and all stats entry points; deleted Heatmap, WeekBars, ChipFilter, stats.ts, StatsPage.
- Verified: `web/` `tsc` + `npm run build` pass.

