import {useEffect, useRef, useState} from 'react'

/**
 * 流式总结时的「跟随到底」浮标。
 *
 * 当 active = true 且用户已经接近页面底部（64px 容差）时，每次 deps 变化（例如 summary
 * 字符数增长）就把视口滚到底；用户主动向上滚则停止跟随并显示「↓ 跳到底」浮标。
 *
 * `awayFromBottomRef` 默认 true（视为「不在底部」），mount 后第一次 scroll 事件或
 * 第一次内容增长会同步真实位置，避免「用户进入 SUMMARIZING 时即使在页面中段阅读
 * 也被强制顶到底」。
 */
export function useStickToBottom(active: boolean, deps: unknown[]) {
  const awayFromBottomRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  // 基于当前 viewport 判断是否「足够靠近底部」（容差 64px）
  const computeNearBottom = () => {
    if (typeof window === 'undefined') return true
    const doc = document.documentElement
    return window.innerHeight + window.scrollY >= doc.scrollHeight - 64
  }

  useEffect(() => {
    if (!active) {
      awayFromBottomRef.current = true
      setShowJump(false)
      return
    }
    // 进入 active 时立刻同步一次真实位置；用户已经在底部才会开启「自动跟随」
    awayFromBottomRef.current = !computeNearBottom()
    setShowJump(awayFromBottomRef.current)
    const onScroll = () => {
      const away = !computeNearBottom()
      awayFromBottomRef.current = away
      setShowJump(away)
    }
    window.addEventListener('scroll', onScroll, {passive: true})
    return () => window.removeEventListener('scroll', onScroll)
  }, [active])

  useEffect(() => {
    if (!active || awayFromBottomRef.current) return
    // 用户处于底部时才自动跟随新内容
    window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'auto'})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ...deps])

  const jumpToBottom = () => {
    window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'smooth'})
  }
  return {showJump, jumpToBottom}
}
