import { test, expect } from 'vitest'
import { SHEET_SNAPS, clampSnap, fractionFromDrag, nearestSnap, stepSnap } from './sheetSnap'
import { batteryClass, contactClass, snrClass, snrGlyph } from './logic'

test('fermi: chiuso, 40%, 78%', () => {
  expect([...SHEET_SNAPS]).toEqual([0, 0.4, 0.78])
})

test('nearestSnap sceglie il fermo piu vicino', () => {
  expect(nearestSnap(0)).toBe(0)
  expect(nearestSnap(0.15)).toBe(0)
  expect(nearestSnap(0.25)).toBe(1)
  expect(nearestSnap(0.4)).toBe(1)
  expect(nearestSnap(0.58)).toBe(1)
  expect(nearestSnap(0.6)).toBe(2)
  expect(nearestSnap(1)).toBe(2)
})

test('stepSnap per i pulsanti non esce dai limiti', () => {
  expect(stepSnap(0, 1)).toBe(1)
  expect(stepSnap(1, 1)).toBe(2)
  expect(stepSnap(2, 1)).toBe(2)
  expect(stepSnap(1, -1)).toBe(0)
  expect(stepSnap(0, -1)).toBe(0)
  expect(clampSnap(NaN)).toBe(1)
})

test('fractionFromDrag: su aumenta, giu riduce, con limiti', () => {
  expect(fractionFromDrag(0.4, -100, 500)).toBeCloseTo(0.6)
  expect(fractionFromDrag(0.4, 100, 500)).toBeCloseTo(0.2)
  expect(fractionFromDrag(0.4, -1000, 500)).toBe(0.78)
  expect(fractionFromDrag(0.4, 1000, 500)).toBe(0)
  expect(fractionFromDrag(0.4, 50, 0)).toBe(0.4)
})

test('classi dei colori di dato', () => {
  expect(snrClass(0)).toBe('good')
  expect(snrClass(-3.5)).toBe('mid')
  expect(snrClass(-10)).toBe('mid')
  expect(snrClass(-10.1)).toBe('bad')
  expect(snrClass(null)).toBe('none')
  expect(snrGlyph('good')).toBe('▲')
  expect(snrGlyph('bad')).toBe('▼')
  expect(contactClass(119)).toBe('fresh')
  expect(contactClass(120)).toBe('recent')
  expect(contactClass(1440)).toBe('old')
  expect(batteryClass(15, false)).toBe('low')
  expect(batteryClass(39, false)).toBe('mid')
  expect(batteryClass(85, false)).toBe('')
  expect(batteryClass(5, true)).toBe('usb')
})
