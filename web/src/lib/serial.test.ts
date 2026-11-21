import { describe, expect, it } from 'vitest'
import { serialRunner } from './serial'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => (resolve = r))
  return { promise, resolve }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

describe('serialRunner', () => {
  it('un solo caricamento alla volta, poi uno solo in più per le richieste arrivate nel frattempo', async () => {
    const runs: ReturnType<typeof deferred>[] = []
    const r = serialRunner(() => {
      const d = deferred()
      runs.push(d)
      return d.promise
    })
    r.trigger()
    r.trigger()
    r.trigger()
    expect(runs.length).toBe(1)
    runs[0].resolve()
    await flush()
    expect(runs.length).toBe(2)
    runs[1].resolve()
    await flush()
    expect(runs.length).toBe(2)
  })

  it('un errore non blocca i caricamenti successivi', async () => {
    let n = 0
    const r = serialRunner(() => {
      n++
      return Promise.reject(new Error('rete'))
    })
    r.trigger()
    await flush()
    r.trigger()
    await flush()
    expect(n).toBe(2)
  })

  it('dopo dispose non riparte', async () => {
    const runs: ReturnType<typeof deferred>[] = []
    const r = serialRunner(() => {
      const d = deferred()
      runs.push(d)
      return d.promise
    })
    r.trigger()
    r.trigger()
    r.dispose()
    runs[0].resolve()
    await flush()
    r.trigger()
    expect(runs.length).toBe(1)
  })
})
