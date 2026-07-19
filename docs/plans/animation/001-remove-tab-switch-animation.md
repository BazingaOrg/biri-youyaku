# 001 — 移除 SummaryTabs 切换时的重挂载位移动画

- **Status**: DONE
- **Commit**: 8855ece
- **Severity**: HIGH
- **Category**: Purpose & frequency / Interruptibility
- **Estimated scope**: 1 file，~2 行

## Problem

tab 切换是高频动作（用户每天几十次），但每次切换都因 `key={tab}` 强制重挂载内容容器并重播 200ms 的 `fade-in-up`（含 8px translateY 位移）。快速连点 tab 时动画从零反复重启，产生可见的位移抖动。高频动作上不应有位移型装饰动画。

```tsx
/* web/src/pages/workspace/SummaryTabs.tsx:45 — current */
<div key={tab} className="animate-fade-in-up">
```

`fade-in-up` 定义（不要改它，其他地方在用）：

```js
/* web/tailwind.config.cjs */
'fade-in-up': {
  '0%': {opacity: '0', transform: 'translateY(8px)'},
  '100%': {opacity: '1', transform: 'translateY(0)'},
},
'fade-in-up': 'fade-in-up 200ms ease-out',
```

## Target

tab 切换即时呈现，无动画、无重挂载：

```tsx
/* target — web/src/pages/workspace/SummaryTabs.tsx:45 */
<div key={tab}>
```

保留 `key={tab}`（NotesView/MindmapView 依赖重挂载重置内部状态——如实测移除 key 后无副作用也可移除，但这超出本计划范围，默认保留）。只删 `className="animate-fade-in-up"`。

## Repo conventions to follow

- 高频面无动画是本仓库既有做法：字幕列表 `SummaryTabs.tsx:159-186` 的 `<li>` 无入场动画，仅瞬时 hover 背景。模仿它。
- `fade-in-up` 继续用于低频的列表首屏入场（`HistoryPage.tsx:425`、`up/VideoRow.tsx:28`），不要动那些。

## Steps

1. `web/src/pages/workspace/SummaryTabs.tsx:45`：删除该 div 的 `className="animate-fade-in-up"`（如 className 只有这一个类，删整个 className 属性）。

## Boundaries

- 只动这一行。不要动 tailwind.config.cjs、不要动其他使用 fade-in-up 的文件。
- 不改 `key={tab}`。
- 不加新依赖。
- 若该行代码与上述摘录不符（已漂移），停止并上报，不要即兴发挥。

## Verification

- **Mechanical**: `cd web && npx tsc --noEmit && npm run build` 均通过。
- **Feel check**: 打开一个已完成任务的 Workspace，快速连点 笔记/脑图/字幕 三个 tab：内容应即时切换，无淡入、无向上位移、无抖动。
- **Done when**: 切 tab 无任何动画，构建通过。
