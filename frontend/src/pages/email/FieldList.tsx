// FieldList, ExplainPanel and CandidatePicker (Artifact 7): extracted fields with tier and "Why";
// clicking a field highlights its phrase in the email; "Correct" re-runs with an override (F09).
import { useState } from 'react'
import { Button, Select, Space } from 'antd'
import type { Overrides } from '../../api/types'
import { Chip, TierTag } from '../../components/Tags'
import { card, sectionLabel } from '../../components/styles'
import { c } from '../../theme'
import type { FieldVM, ProposalVM } from '../../vm/viewModels'

const SOURCE_LABEL: Record<string, string> = {
  subject: 'the subject line',
  new_text: 'the email text',
  quoted_text: 'an earlier message in the thread',
  attachments: 'the attachment names',
  kb: 'the vessel and voyage records',
}

function Explain({ field }: { field: FieldVM }) {
  return (
    <div style={{ background: c.surface2, borderRadius: 8, padding: '8px 10px', fontSize: 12, color: c.muted, display: 'grid', gridTemplateColumns: '84px 1fr', gap: '4px 8px' }}>
      <b style={{ color: c.text }}>Evidence</b>
      <span>{field.evidence ? <>“{field.evidence.quote}” in {SOURCE_LABEL[field.evidence.source] ?? field.evidence.source}</> : 'No quote; decided by rule'}</span>
      <b style={{ color: c.text }}>Basis</b>
      <span style={{ overflowWrap: 'anywhere' }}>{field.basisLabel || '—'}</span>
      <b style={{ color: c.text }}>Confidence</b>
      <span>{field.tier ?? 'Not scored'}{field.setBy === 'officer' ? ' · set by you' : ''}</span>
    </div>
  )
}

function FieldRow({ field, highlighted, explainOpen, onHighlight, onExplain }: {
  field: FieldVM; highlighted: boolean; explainOpen: boolean; onHighlight: () => void; onExplain: () => void
}) {
  const canHighlight = Boolean(field.evidence && field.evidence.source !== 'subject')
  return (
    <div style={{ padding: '6px 0', borderBottom: `1px solid ${c.border}`, display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <span style={{ color: c.muted, fontSize: 13 }}>{field.label}</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={canHighlight ? onHighlight : undefined}
            disabled={!canHighlight}
            title={canHighlight ? 'Show the phrase in the email' : undefined}
            style={{ border: 0, background: highlighted ? c.amberBg : 'transparent', borderRadius: 4, padding: '0 4px', fontFamily: 'inherit', fontSize: 13, fontWeight: 500, color: c.text, cursor: canHighlight ? 'pointer' : 'default', textAlign: 'right', textDecoration: canHighlight ? 'underline dotted' : 'none' }}
          >
            {field.value}
          </button>
          <TierTag tier={field.tier} />
          {field.setBy === 'officer' && <Chip tone="you">You</Chip>}
          <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }} onClick={onExplain} aria-expanded={explainOpen}>
            Why
          </Button>
        </span>
      </div>
      {explainOpen && <Explain field={field} />}
    </div>
  )
}

export interface CorrectOptions {
  vessels: { code: string; voyages: string[] }[]
  eventTypes: string[]
}

function Correct({ proposal, options, busy, onRerun }: { proposal: ProposalVM; options: CorrectOptions; busy: boolean; onRerun: (o: Overrides) => void }) {
  const current = (k: string) => proposal.fields.find((f) => f.key === k)?.value
  const [vessel, setVessel] = useState<string | undefined>()
  const [voyage, setVoyage] = useState<string | undefined>()
  const [event, setEvent] = useState<string | undefined>()
  const vesselCode = vessel ?? current('vessel')
  const voyages = options.vessels.find((v) => v.code === vesselCode)?.voyages ?? []
  const changed = vessel || voyage || event
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
      <Space wrap size={6}>
        <Select size="small" placeholder="Vessel" style={{ width: 110 }} value={vessel} onChange={(v) => { setVessel(v); setVoyage(undefined) }}
          options={options.vessels.map((v) => ({ value: v.code, label: v.code }))} aria-label="Correct vessel" />
        <Select size="small" placeholder="Voyage" style={{ width: 100 }} value={voyage} onChange={setVoyage}
          options={voyages.map((v) => ({ value: v, label: v }))} aria-label="Correct voyage" />
        <Select size="small" placeholder="Event type" style={{ width: 230 }} value={event} onChange={setEvent} showSearch
          options={options.eventTypes.map((e) => ({ value: e, label: e }))} aria-label="Correct event type" popupMatchSelectWidth={320} />
      </Space>
      <div>
        <Button size="small" type="primary" ghost disabled={!changed} loading={busy}
          onClick={() => onRerun({ vessel_code: vessel ?? null, voyage_no: voyage ?? null, event_type: event ?? null })}>
          Re-run with my correction
        </Button>
      </div>
    </div>
  )
}

export function FieldList({ proposal, highlightedField, explainOpenFor, onHighlight, onExplain, options, busy, onRerun }: {
  proposal: ProposalVM
  highlightedField: string | null
  explainOpenFor: string | null
  onHighlight: (key: string) => void
  onExplain: (key: string) => void
  options: CorrectOptions
  busy: boolean
  onRerun: (o: Overrides) => void
}) {
  const [correcting, setCorrecting] = useState(false)
  const context = proposal.fields.filter((f) => ['vessel', 'voyage', 'contract'].includes(f.key))
  const extracted = proposal.fields.filter((f) => !['vessel', 'voyage', 'contract'].includes(f.key))
  const row = (f: FieldVM) => (
    <FieldRow key={f.key} field={f} highlighted={highlightedField === f.key} explainOpen={explainOpenFor === f.key}
      onHighlight={() => onHighlight(f.key)} onExplain={() => onExplain(f.key)} />
  )
  const vesselCandidates = proposal.candidates.filter((x) => x.kind === 'vessel')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <span style={sectionLabel}>Extracted from email</span>
          <Chip tone="accent">From email</Chip>
        </div>
        {extracted.map(row)}
        {extracted.length === 1 && (
          <div style={{ fontSize: 12, color: c.muted, paddingTop: 6 }}>No dates or quantities changed by this email.</div>
        )}
      </div>
      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <span style={sectionLabel}>Matched context</span>
          <Chip>Master data</Chip>
        </div>
        {context.map(row)}
        {vesselCandidates.length > 0 && proposal.status === 'open' && (
          <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: c.amber }}>Which vessel is it? Choose one to re-run:</span>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {vesselCandidates.map((v) => (
                <Button key={v.value} onClick={() => onRerun({ vessel_code: v.value })} loading={busy}>
                  {v.label}{v.score != null ? ` · score ${v.score.toFixed(2)}` : ''}
                </Button>
              ))}
            </div>
          </div>
        )}
        {proposal.status === 'open' && (
          <div style={{ marginTop: 8 }}>
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setCorrecting((v) => !v)}>
              {correcting ? 'Cancel correction' : 'Wrong vessel, voyage or event? Correct it'}
            </Button>
            {correcting && <Correct proposal={proposal} options={options} busy={busy} onRerun={onRerun} />}
          </div>
        )}
      </div>
    </div>
  )
}
