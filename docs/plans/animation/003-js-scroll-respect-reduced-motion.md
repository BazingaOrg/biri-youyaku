# 003 — JS 平滑滚动尊重 prefers-reduced-motion

- **Status**: DONE
- **Commit**: 8855ece
- **Severity**: HIGH
- **Category**: Accessibility
- **Estimated scope**: 4 files（新建 1 + 修改 3），~20 行

## Problem

全局 reduced-motion 降级（`web/src/styles.css:138-147`）只覆盖 CSS 的 `scroll-behavior`；三处 JS 显式传 `behavior:'smooth'` 完全绕过它，开启"减弱动态效果"的用户仍会看到平滑滚动（前庭敏感用户的实际伤害点）：

```tsx
/* web/src/components/ScrollToTop.tsx:19 — current */
onClick={() => window.scrollTo({top: 0, behavior: 'smooth'})}
```

```ts
/* web/src/hooks/useStickToBottom.ts:50 — current */
window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'smooth'})
```

```tsx
/* web/src/pages/workspace/SummaryTabs.tsx:96 — current */
window.scrollTo({top, behavior: 'smooth'})
```

注意 `useStickToBottom.ts:45` 用的是 `behavior:'auto'`，是对的，不要动。

## Target

新建一个小工具，读取媒体查询决定滚动行为，三处统一改用：

```ts
/* target — 新文件 web/src/lib/scroll.ts */
/** 尊重系统"减弱动态效果"的平滑滚动：reduce 时退化为瞬时跳转。 */
export function smoothScrollTo(options: ScrollToOptions) {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({...options, behavior: reduce ? 'auto' : 'smooth'})
}
```

三处调用点改为：

```tsx
smoothScrollTo({top: 0})                                          // ScrollToTop.tsx
smoothScrollTo({top: document.documentElement.scrollHeight})      // useStickToBottom.ts:50
smoothScrollTo({top})                                             // SummaryTabs.tsx:96
```

每次调用时实时查 `matchMedia`（不缓存），保证用户中途切换系统设置立即生效；调用频率低，无性能顾虑。

## Repo conventions to follow

- 工具函数放 `web/src/lib/`（已有 `api.ts`、`sse.ts`、`markdown.ts` 等），具名导出，文件短小单一职责。
- 注释中文、说明为什么，参考 `web/src/lib/activeJob.ts` 的风格。

## Steps

1. 新建 `web/src/lib/scroll.ts`，内容如上 target。
2. `web/src/components/ScrollToTop.tsx`：import `smoothScrollTo`，`:19` 改为 `onClick={() => smoothScrollTo({top: 0})}`。
3. `web/src/hooks/useStickToBottom.ts`：import，`:50` 的调用替换；`:45` 的 `'auto'` 调用保持原样。
4. `web/src/pages/workspace/SummaryTabs.tsx`：import，`:96` 替换。

## Boundaries

- 不动 `styles.css` 的全局降级。
- 不动其他任何 `scrollTo`/`scrollIntoView` 调用（如有 `behavior:'auto'` 的，本来就合规）。
- 不加依赖、不引入 hook 形态（无需响应式订阅，函数式实时查询足够）。
- 若调用点代码与摘录不符，停止并上报。

## Verification

- **Mechanical**: `cd web && npx tsc --noEmit && npm run build` 通过；`grep -rn "behavior: 'smooth'" web/src` 应只剩 `lib/scroll.ts` 一处。
- **Feel check**: DevTools → Rendering → Emulate `prefers-reduced-motion: reduce`：点"回到顶部"、目录跳转、跳到底部，均应瞬时跳转无平滑滚动；关闭模拟后恢复平滑。
- **Done when**: 三个调用点走工具函数，reduce 模拟下无平滑滚动，构建通过。
