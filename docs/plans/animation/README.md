# 动画改进计划（improve-animations 审计产出）

审计基线 commit：`8855ece`。计划自包含，可交给任意 agent 执行；执行前若代码已漂移，以计划内的 STOP 规则为准。

| # | 计划 | 严重度 | 状态 |
|---|---|---|---|
| 001 | [移除 SummaryTabs 切换位移动画](001-remove-tab-switch-animation.md) | HIGH | DONE |
| 002 | [pop-out 改 ease-out，兜底定时器对齐](002-pop-out-ease-out-and-timer-align.md) | HIGH | DONE |
| 003 | [JS 平滑滚动尊重 reduced-motion](003-js-scroll-respect-reduced-motion.md) | HIGH | DONE |

## 执行顺序与依赖

三份计划互不依赖，可任意顺序或并行执行。建议 001 → 002 → 003（按用户感知频率）。

## 未立项的审计发现（备查）

- MEDIUM：StepCarousel `transition-all`+width、进度条 width→scaleX、duration/easing token 收敛
- LOW：IconTooltip 触发源生长、toast keyframe 不可反向、MindmapView/ChipFilter 布局硬跳
- 机会点：RUNNING→COMPLETED 的 DoneView 入场承接（全站唯一值得 delight 预算处）、删除行塌缩、阶段切换 fade
