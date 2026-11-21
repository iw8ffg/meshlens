/**
 * Esecuzione in fila di un caricamento: se è già in corso, la richiesta si ricorda e il
 * caricamento riparte una sola volta alla fine, così i risultati non arrivano fuori ordine.
 */
export function serialRunner(run: () => Promise<unknown>): { trigger: () => void; dispose: () => void } {
  let running = false
  let again = false
  let disposed = false
  const trigger = () => {
    if (disposed) return
    if (running) {
      again = true
      return
    }
    running = true
    again = false
    run()
      .catch(() => {})
      .finally(() => {
        running = false
        if (again) trigger()
      })
  }
  return {
    trigger,
    dispose: () => {
      disposed = true
    },
  }
}
