/** 尊重系统「减弱动态效果」的滚动行为：reduce 时退化为瞬时跳转。 */
export function preferredScrollBehavior(): ScrollBehavior {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

export function smoothScrollTo(options: ScrollToOptions) {
  window.scrollTo({...options, behavior: preferredScrollBehavior()})
}
