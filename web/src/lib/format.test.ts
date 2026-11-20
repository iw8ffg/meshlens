import { test, expect } from 'vitest'
import { timeAgo, flag, formatDate, compareLastHeard } from './format'

const now = 1_000_000

test('format', () => {
  expect(timeAgo(now - 30, now)).toBe('adesso')
  expect(timeAgo(now - 300, now)).toBe('5 min fa')
  expect(timeAgo(now - 3 * 3600, now)).toBe('3 h fa')
  expect(timeAgo(now - 2 * 86400, now)).toBe('2 g fa')
  expect(flag('IT')).toBe('🇮🇹')
  expect(flag(null)).toBe('🏳️')
})

test('last_heard null', () => {
  expect(timeAgo(null, now)).toBe('mai')
  expect(timeAgo(NaN, now)).toBe('mai')
  expect(formatDate(null)).toBe('mai')
  expect(formatDate(now)).not.toContain('NaN')
  expect([null, 5, 9, null].sort(compareLastHeard)).toEqual([9, 5, null, null])
})
