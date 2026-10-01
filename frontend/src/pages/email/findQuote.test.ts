import { describe, expect, it } from 'vitest'
import { findQuote } from './findQuote'

describe('findQuote', () => {
  const text = 'Please kindly find the ROB calculation:\n3. Arrival Discharge Port\n  Distance 1400nm including 80nm ECA'
  it('f_vm_quote_finds_a_passage_across_line_breaks_and_case', () => {
    const at = findQuote(text, 'arrival discharge port distance 1400NM')
    expect(at && text.slice(at[0], at[1])).toBe('Arrival Discharge Port\n  Distance 1400nm')
  })
  it('f_vm_quote_uses_the_first_fragment_of_an_ellipsis_quote_and_ignores_short_or_missing_ones', () => {
    expect(findQuote(text, 'Please kindly find ... ECA')).not.toBeNull()
    expect(findQuote(text, 'ECA')).toBeNull()
    expect(findQuote(text, 'Berth schedule confirmed')).toBeNull()
    expect(findQuote(text, null)).toBeNull()
  })
})
