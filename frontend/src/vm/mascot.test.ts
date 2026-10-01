import { describe, expect, it } from 'vitest'
import { moodOf } from './mascot'

describe('Mascot mood (U11)', () => {
  it('f_vm_mascot_many_some_few_todos', () => {
    expect([moodOf(33), moodOf(21), moodOf(20), moodOf(8), moodOf(7), moodOf(0)]).toEqual(['tired', 'tired', 'calm', 'calm', 'eating', 'eating'])
  })
})
