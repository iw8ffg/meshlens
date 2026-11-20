import { test, expect } from 'vitest'
import { sortPorts, stateClass, stateLabel } from './radios'
import type { Port } from './types'

const p = (device: string, likely: boolean): Port => ({
  device,
  description: '',
  vid: null,
  pid: null,
  likely_meshtastic: likely,
  in_use_by: null,
})

test('sortPorts: probabili prima, poi ordine naturale, input intatto', () => {
  const input = [p('COM10', false), p('COM3', true), p('COM2', false), p('COM7', true)]
  expect(sortPorts(input).map((x) => x.device)).toEqual(['COM3', 'COM7', 'COM2', 'COM10'])
  expect(input[0].device).toBe('COM10')
})

test('stateClass', () => {
  expect(stateClass('connected')).toBe('green')
  expect(stateClass('connecting')).toBe('yellow')
  expect(stateClass('reconnecting')).toBe('yellow')
  expect(stateClass('error')).toBe('red')
  expect(stateClass('disconnected')).toBe('gray')
})

test('stateLabel', () => {
  expect(stateLabel('connected')).toBe('Connessa')
  expect(stateLabel('disconnected')).toBe('Scollegata')
})
