import { afterEach, expect, test, vi } from 'vitest'
import { copyText } from './clipboard'

afterEach(() => vi.unstubAllGlobals())

function fakeDoc(exec: () => boolean) {
  const ta = { value: '', style: {} as Record<string, string>, setAttribute: vi.fn(), select: vi.fn(), remove: vi.fn() }
  const doc = {
    createElement: vi.fn(() => ta),
    body: { appendChild: vi.fn() },
    execCommand: vi.fn(exec),
  }
  return { doc: doc as unknown as Document, ta, raw: doc }
}

test('usa navigator.clipboard in contesto sicuro', async () => {
  vi.stubGlobal('window', { isSecureContext: true })
  const writeText = vi.fn().mockResolvedValue(undefined)
  expect(await copyText('ciao', { clipboard: { writeText } } as never, null)).toBe(true)
  expect(writeText).toHaveBeenCalledWith('ciao')
})

test('ricade su execCommand e rimuove la textarea', async () => {
  vi.stubGlobal('window', { isSecureContext: false })
  const { doc, ta, raw } = fakeDoc(() => true)
  expect(await copyText('x', null, doc)).toBe(true)
  expect(ta.value).toBe('x')
  expect(raw.execCommand).toHaveBeenCalledWith('copy')
  expect(ta.remove).toHaveBeenCalled()
})

test('execCommand che lancia -> false, textarea rimossa', async () => {
  vi.stubGlobal('window', { isSecureContext: false })
  const { doc, ta } = fakeDoc(() => {
    throw new Error('no')
  })
  expect(await copyText('x', null, doc)).toBe(false)
  expect(ta.remove).toHaveBeenCalled()
})

test('writeText che fallisce ricade su execCommand', async () => {
  vi.stubGlobal('window', { isSecureContext: true })
  const { doc } = fakeDoc(() => true)
  const writeText = vi.fn().mockRejectedValue(new Error('denied'))
  expect(await copyText('x', { clipboard: { writeText } } as never, doc)).toBe(true)
})
