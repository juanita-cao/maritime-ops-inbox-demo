/** Where a chat quote sits in a text: whitespace-tolerant, case-insensitive; "..." splits fragments. */
export function findQuote(text: string, quote: string | null): [number, number] | null {
  if (!quote) return null
  const first = quote.split(/\.{3}|…/).map((x) => x.trim()).filter((x) => x.length >= 8)[0]
  if (!first) return null
  const pattern = first.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('\\s+')
  const m = new RegExp(pattern, 'i').exec(text)
  return m ? [m.index, m.index + m[0].length] : null
}
