/** 尊重系统「减弱动态效果」的平滑滚动：reduce 时退化为瞬时跳转。 */
export function smoothScrollTo(options: ScrollToOptions) {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({...options, behavior: reduce ? 'auto' : 'smooth'})
}
