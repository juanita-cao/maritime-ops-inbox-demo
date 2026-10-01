// Small shared badges: status pill, priority badge (U1), tier chip, plain chip.
import type { CSSProperties, ReactNode } from 'react'
import type { NeedsAction, Tier } from '../api/types'
import { HIGH_PRIORITY, LOW_PRIORITY, STATUS_COLORS, c, type Pair } from '../theme'
import { isHighlighted } from '../vm/viewModels'

const pill: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 10px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: 'nowrap',
  lineHeight: '18px',
}

export function Pill({ pair, children, title }: { pair: Pair; children: ReactNode; title?: string }) {
  return (
    <span title={title} style={{ ...pill, color: pair.fg, background: pair.bg }}>
      {children}
    </span>
  )
}

const SHORT: Partial<Record<NeedsAction, string>> = {
  'Approval Required': 'Approval',
  'Waiting for Reply': 'Reply',
}

export function StatusTag({ status, short = false }: { status: NeedsAction; short?: boolean }) {
  return (
    <Pill pair={STATUS_COLORS[status]} title={status}>
      {short ? (SHORT[status] ?? status) : status}
    </Pill>
  )
}

export function StatusTags({ statuses }: { statuses: NeedsAction[] }) {
  return (
    <>
      {statuses.map((s, i) => (
        <StatusTag key={s} status={s} short={statuses.length > 1 && i > 0} />
      ))}
    </>
  )
}

export function PriorityBadge({ priority }: { priority: number | null }) {
  if (priority == null) return null
  const pair = isHighlighted(priority) ? HIGH_PRIORITY : LOW_PRIORITY
  return (
    <span title={`Priority ${priority} of 5`} style={{ ...pill, padding: '2px 8px', fontWeight: 700, color: pair.fg, background: pair.bg }}>
      P{priority}
    </span>
  )
}

const TIER_PAIR: Record<Tier, Pair> = {
  High: { fg: c.green, bg: c.greenBg },
  Medium: { fg: c.amber, bg: c.amberBg },
  Low: { fg: c.red, bg: c.redBg },
}

export function TierTag({ tier }: { tier: Tier | null }) {
  if (!tier) return null
  return (
    <span style={{ ...pill, padding: '0 7px', fontSize: 11, borderRadius: 6, color: TIER_PAIR[tier].fg, background: TIER_PAIR[tier].bg }}>
      {tier}
    </span>
  )
}

export function Chip({ children, tone = 'gray' }: { children: ReactNode; tone?: 'gray' | 'accent' | 'you' }) {
  const pair: Pair =
    tone === 'accent' || tone === 'you' ? { fg: c.accent, bg: c.accentBg } : LOW_PRIORITY
  return (
    <span style={{ ...pill, padding: '0 7px', fontSize: 11, borderRadius: 6, color: pair.fg, background: pair.bg }}>
      {children}
    </span>
  )
}
