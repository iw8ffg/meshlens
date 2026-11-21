/** Copia negli appunti; in HTTP (contesto non sicuro) ricade su execCommand. Non lancia mai. */
export async function copyText(
  text: string,
  nav: Pick<Navigator, 'clipboard'> | null = typeof navigator === 'undefined' ? null : navigator,
  doc: Document | null = typeof document === 'undefined' ? null : document,
): Promise<boolean> {
  const secure = typeof window !== 'undefined' && window.isSecureContext
  if (secure && nav?.clipboard) {
    try {
      await nav.clipboard.writeText(text)
      return true
    } catch {
      // permesso negato: si prova il ripiego
    }
  }
  if (!doc) return false
  let ta: HTMLTextAreaElement | null = null
  try {
    ta = doc.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    doc.body.appendChild(ta)
    ta.select()
    return doc.execCommand('copy')
  } catch {
    return false
  } finally {
    ta?.remove()
  }
}
