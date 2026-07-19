# 002 — pop-out 改 ease-out，兜底定时器与动画时长对齐

- **Status**: DONE
- **Commit**: 8855ece
- **Severity**: HIGH
- **Category**: Easing & duration / Cohesion
- **Estimated scope**: 3 files，~4 行

## Problem

1. 离场动画 `pop-out` 用 `ease-in`：起步最慢的瞬间恰是用户正注视元素离场的瞬间，感知为迟钝。UI 上的 ease-in 一律是 finding；离场同样应 ease-out（快速启动、平缓收尾）。

```js
/* web/tailwind.config.cjs — current */
animation: {
  pop: 'pop 180ms ease-out',
  'pop-out': 'pop-out 150ms ease-in',
  ...
}
```

2. 两处离场兜底定时器硬编码 200ms，与动画实际 150ms 各写各的；日后改时长会漂移：

```tsx
/* web/src/components/ConfirmDialog.tsx:53 — current */
closeTimerRef.current = setTimeout(() => setClosing(false), 200)
```

```tsx
/* web/src/components/ToastProvider.tsx:56 — current */
window.setTimeout(() => remove(id), 200)
```

## Target

```js
/* target — web/tailwind.config.cjs */
'pop-out': 'pop-out 150ms ease-out',
```

两处兜底定时器改为共享常量，值 = 动画时长 + 50ms 余量：

```ts
/* target — 每个文件内各自定义（两个文件不互相 import） */
const POP_OUT_FALLBACK_MS = 200 // pop-out 150ms + 50ms 余量；改动画时长时同步改这里
```

即数值不变（200），但改为具名常量 + 注释说明推导关系，两处都用该常量替换裸 200。

## Repo conventions to follow

- 入场 `pop: 'pop 180ms ease-out'` 就是正确示范；离场对齐它的缓动方向。
- 该仓库注释风格是中文、说明"为什么"，参考 `ConfirmDialog.tsx` 现有注释。

## Steps

1. `web/tailwind.config.cjs`：`'pop-out': 'pop-out 150ms ease-in'` → `'pop-out': 'pop-out 150ms ease-out'`。
2. `web/src/components/ConfirmDialog.tsx`：文件顶部（import 之后）加 `const POP_OUT_FALLBACK_MS = 200`（带上述注释）；`:53` 的 `200` 换成该常量。
3. `web/src/components/ToastProvider.tsx`：同样加常量；`:56` 的 `200` 换成该常量。

## Boundaries

- 不改 keyframe 定义本身（`pop-out` 的 0%/100% 帧不动）。
- 不改 `onAnimationEnd` 逻辑。
- 不加新依赖、不新建共享模块（两个常量各自文件内定义即可，避免为 4 行代码建 util）。
- 若代码与摘录不符，停止并上报。

## Verification

- **Mechanical**: `cd web && npx tsc --noEmit && npm run build` 通过。
- **Feel check**: 打开历史页删除一条记录触发 ConfirmDialog，点取消：弹窗应"迅速启动收缩、柔和结束"，不再有起步迟滞感。DevTools Animations 面板调 10% 播放速度对比确认离场曲线前快后慢。触发一条 toast 等它自动消失，观感一致。
- **Done when**: 离场曲线为 ease-out，两处定时器引用具名常量，构建通过。
