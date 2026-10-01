// FilterChips and InboxList (Artifact 7): rows only dispatch events.
import type { CSSProperties } from 'react'
import { Empty } from 'antd'
import { Pill, PriorityBadge, StatusTags } from '../../components/Tags'
import { HIGHLIGHT_STYLE, NOT_MATCHED, c } from '../../theme'
import { FILTERS, matchesFilter, type InboxFilter, type InboxRowVM } from '../../vm/viewModels'


const LABEL: Partial<Record<InboxFilter, string>> = { 'FYI - No Action': 'FYI' }

export function FilterChips({ rows, filter, onChange }: { rows: InboxRowVM[]; filter: InboxFilter; onChange: (f: InboxFilter) => void }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {FILTERS.map((f) => {
        const on = f === filter
        const style: CSSProperties = {
          display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 999, fontSize: 13,
          fontWeight: 500, minHeight: 34, cursor: 'pointer', fontFamily: 'inherit',
          border: `1px solid ${on ? c.accent : c.border}`,
          background: on ? c.accentBg : c.surface,
          color: on ? c.accent : c.text,
        }
        return (
          <button key={f} type="button" style={style} onClick={() => onChange(f)} aria-pressed={on}>
            {LABEL[f] ?? f}
            {f !== 'All' && <b style={{ fontWeight: 600 }}>{rows.filter((r) => matchesFilter(r, f)).length}</b>}
          </button>
        )
      })}
    </div>
  )
}

function Row({ row, selected, onSelect }: { row: InboxRowVM; selected: boolean; onSelect: () => void }) {
  const notMatched = row.reviewStatus === 'Not matched' || row.reviewStatus === 'Held'
  const style: CSSProperties = {
    textAlign: 'left', width: '100%', fontFamily: 'inherit', cursor: 'pointer', color: c.text,
    borderRadius: 10, padding: '11px 13px', display: 'flex', flexDirection: 'column', gap: 4,
    border: `1px solid ${c.border}`, background: c.surface,
    ...(row.highlighted ? HIGHLIGHT_STYLE : {}),
    ...(selected ? { background: c.accentBg, borderColor: c.accent } : {}),
  }
  const reviewColor = row.reviewStatus === 'To review' ? c.accent : notMatched ? c.amber : c.muted
  return (
    <button type="button" style={style} onClick={onSelect} aria-current={selected}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, width: '100%' }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: notMatched ? c.amber : c.accent }}>
          {row.vesselCode ? `${row.vesselCode}${row.voyageNo ? ` · ${row.voyageNo}` : ''}` : 'Vessel not identified'}
        </span>
        <span style={{ fontSize: 12, color: c.muted, whiteSpace: 'nowrap' }}>
          {row.sentDate} · <span style={{ fontWeight: row.reviewStatus === 'Reviewed' ? 400 : 600, color: reviewColor }}>{row.reviewStatus}</span>
        </span>
      </div>
      <div style={{ fontWeight: 600, fontSize: 14, overflowWrap: 'anywhere' }}>{row.subject}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', width: '100%' }}>
        <span style={{ fontSize: 12, color: c.muted }}>
          {row.heldReason ?? [row.senderRole, row.eventType].filter(Boolean).join(' · ')}
        </span>
        <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
          {row.reviewStatus === 'Held' ? (
            <Pill pair={NOT_MATCHED}>Held</Pill>
          ) : row.reviewStatus === 'Not matched' ? (
            <Pill pair={NOT_MATCHED}>Not matched</Pill>
          ) : (
            <>
              {!row.isReport && <PriorityBadge priority={row.priority} />}
              <StatusTags statuses={row.statuses} />
            </>
          )}
        </span>
      </div>
    </button>
  )
}

export function InboxList({ rows, selectedId, onSelect }: { rows: InboxRowVM[]; selectedId: string | null; onSelect: (id: string) => void }) {
  if (rows.length === 0) return <Empty description="No emails here" style={{ marginTop: 40 }} />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {rows.map((r) => (
        <Row key={r.emailId} row={r} selected={r.emailId === selectedId} onSelect={() => onSelect(r.emailId)} />
      ))}
    </div>
  )
}
