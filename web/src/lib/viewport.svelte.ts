// Telefono vs desktop: una sola classe `vp-phone` sul documento, decisa da matchMedia.
export const PHONE_QUERY = '(max-width: 820px)'

export const viewport = $state({ phone: false })

/** Registra il listener e imposta la classe su <html>. Restituisce il cleanup. */
export function initViewport(): () => void {
  const mq = window.matchMedia(PHONE_QUERY)
  const apply = (matches: boolean) => {
    viewport.phone = matches
    document.documentElement.classList.toggle('vp-phone', matches)
  }
  const onChange = (e: MediaQueryListEvent) => apply(e.matches)
  apply(mq.matches)
  mq.addEventListener('change', onChange)
  return () => {
    mq.removeEventListener('change', onChange)
    document.documentElement.classList.remove('vp-phone')
  }
}
