import { test, expect, afterEach } from 'vitest'
import { setLang } from './i18n/index.svelte'
import { timeAgo, formatDate, compareLastHeard, num, signed, ago } from './format'

const now = 1_000_000

afterEach(() => setLang('it'))

test('format', () => {
  expect(timeAgo(now - 30, now)).toBe('adesso')
  expect(timeAgo(now - 300, now)).toBe('5 min fa')
  expect(timeAgo(now - 3 * 3600, now)).toBe('3 h fa')
  expect(timeAgo(now - 2 * 86400, now)).toBe('2 g fa')
})

test('last_heard null', () => {
  expect(timeAgo(null, now)).toBe('mai')
  expect(timeAgo(NaN, now)).toBe('mai')
  expect(formatDate(null)).toBe('mai')
  expect(formatDate(now)).not.toContain('NaN')
  expect([null, 5, 9, null].sort(compareLastHeard)).toEqual([9, 5, null, null])
})

test('num, signed, ago (formato del design)', () => {
  expect(`${num(3.59, 2)} V`).toBe('3,59 V')
  expect(num(3)).toBe('3')
  expect(num(1234.5, 1)).toBe('1234,5')
  expect(`${signed(-3.5, 1)} dB`).toBe('−3,5 dB')
  expect(signed(6.5, 1)).toBe('+6,5')
  expect(signed(0, 1)).toBe('0,0')
  expect(signed(-0.04, 1)).toBe('0,0')
  expect(ago(12)).toBe('12 min fa')
  expect(ago(0.2)).toBe('ora')
  expect(ago(59.9)).toBe('59 min fa')
  expect(ago(60)).toBe('1 h fa')
  expect(ago(1439)).toBe('23 h fa')
  expect(ago(1440)).toBe('1 g fa')
  expect(ago(null)).toBe('mai')
})

test('formati in inglese (en-GB): punto decimale, meno tipografico, 24 ore', () => {
  setLang('en')
  expect(`${num(3.59, 2)} V`).toBe('3.59 V')
  expect(`${signed(-3.5, 1)} dB`).toBe('−3.5 dB')
  expect(signed(6.5, 1)).toBe('+6.5')
  expect(signed(-0.04, 1)).toBe('0.0')
  expect(num(1234.5, 1)).toBe('1,234.5')
  expect(ago(12)).toBe('12 min ago')
  expect(ago(0.2)).toBe('now')
  expect(ago(1440)).toBe('1 d ago')
  expect(ago(null)).toBe('never')
  expect(timeAgo(now - 30, now)).toBe('just now')
  expect(timeAgo(now - 3 * 3600, now)).toBe('3 h ago')
  expect(formatDate(null)).toBe('never')
  // 15:04 UTC del 14 marzo 2024: orario a 24 ore, senza AM/PM
  const d = formatDate(Date.UTC(2024, 2, 14, 15, 4, 0) / 1000)
  expect(d).not.toMatch(/AM|PM/i)
  expect(d).toMatch(/\d{2}:\d{2}:\d{2}$/)
})
