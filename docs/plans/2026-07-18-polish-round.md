# 2026-07-18 打磨轮：UI/UX、结构、性能、缓存清理、README 对齐

## 背景摸底结论

- 前端：API 集中于 `lib/api.ts`、SSE 已 rAF 节流、reduced-motion 已处理、三态覆盖完整。问题：动画极少、无 skeleton、NotesView 裸 window-scroll 高亮、HistoryPage(601行)/UpPage(496行) 职责混杂、无路由级 code-splitting、历史/统计页阻塞式全量拉取。
- 后端：分层清晰。问题：VACUUM/WAL checkpoint 同步阻塞事件循环（cleanup.py:150-165）；routes/jobs.py 依赖 routes/config.py 私有函数；蒸馏语料 `data/distill/<mid>/` 无任何清理路径（cleanup 不扫、无 DELETE 端点、`distill/repo.py delete_run` 为死代码）。
- 文档：README 缺蒸馏/统计页/音频下载任务/resummarize/force_asr；CONFIG.md 与 config.py 脱节；mermaid 架构图过时。

## 决策（已确认）

- 蒸馏并发化、distill→jobs 事件驱动重构：本轮不做，留待下轮（需 deep-reasoner 先出方案）。
- 蒸馏语料只加手动删除 + 孤儿扫描，不加自动保留期。

## 执行步骤

1. [x] 写本计划文档
2. [x] 前端：拆分 HistoryPage/UpPage 子组件；进场/tab 过渡动画（遵守 reduced-motion）；skeleton 替代转圈；NotesView 改 IntersectionObserver；路由 lazy；历史/统计页首页先渲染后台续拉
3. [x] 后端：VACUUM/checkpoint 移入 to_thread；_validate_llm_base_url 下沉共享模块；孤儿扫描纳入 distill_storage_dir；新增 DELETE /v1/up/{mid}/distill + 测试
4. [x] 文档：README.md/README.en.md 补齐蒸馏/统计/音频下载/补救特性并更新架构图；CONFIG.md 补 DISTILL_STORAGE_DIR
5. [x] qa-runner 全量验证：pytest、tsc/build、lint

## 实现记录

- 前端：IconTooltip/ChipFilter 拆到 pages/history/，UpList/DistillButton/VideoRow 拆到 pages/up/；新增 Skeleton 组件与 fade-in-up 进场动画（带封顶 stagger）；SummaryTabs 目录高亮改 IntersectionObserver、tab 切换加 fade；三个路由页改 lazy+Suspense；历史/统计页改为首页立即渲染+后台续拉（统计聚合完成前显示"加载中"避免误导）。
- 后端：VACUUM/checkpoint 经 asyncio.to_thread 执行（单例连接 check_same_thread=False）；validate_llm_base_url 下沉到 biri_youyaku/llm_url.py；scan_orphans_once 纳入 distill 孤儿目录（遵守 orphan_file_retention_days）；新增 DELETE /v1/up/{mid}/distill（活跃 run 409）+ web api.ts 的 deleteDistill；新增 5 个测试。
- 文档：README 双语补 4 项特性（蒸馏语料/统计页/任务补救/音频下载），mermaid 图加 distill/stats；CONFIG.md 补 DISTILL_STORAGE_DIR（其余项核对已同步）。CONFIG.md 未改为粗粒度 4 组布局——现有更细分组已覆盖，保持 surgical。
- 偏差：文档 agent 曾误回滚并行 agent 的半成品文件，已恢复；最终各 agent 自查确认无丢失。
- 验证：pytest 133 passed、ruff 通过、tsc 无错误、npm run build 成功（lazy chunk 拆分生效）；web 无 lint 脚本。
- 遗留（下轮候选）：蒸馏转写串行改并发、distill→jobs 轮询式集成改事件驱动；DELETE distill 的 UI 入口未加（仅 API 层）。
