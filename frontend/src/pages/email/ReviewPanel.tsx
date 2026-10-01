// "Your review" (Artifact 7): StatusPicker (U2), ActionList with PriorityPicker and DuePicker (U1),
// TaskCompare, DecisionBar. Components only call the handlers they get; guards live in F-State.
import { useState, type CSSProperties } from 'react'
import { Alert, Button, Input, Select, Tooltip } from 'antd'
import { MinusOutlined, PlusOutlined } from '@ant-design/icons'
import { DUE_TYPES, STATUS_ORDER, type DueType, type NeedsAction } from '../../api/types'
import { Chip, Pill, StatusTag } from '../../components/Tags'
import { card, sectionLabel } from '../../components/styles'
import { DONE, HIGHLIGHT_STYLE, NOT_MATCHED, STATUS_COLORS, c } from '../../theme'
import type { ActionPatch } from '../../state/reducer'
import { isHighlighted, type ActionEditVM, type ProposalVM } from '../../vm/viewModels'

const step: CSSProperties = {
  width: 22, height: 22, flexShrink: 0, borderRadius: 999, background: c.accentBg, color: c.accent, fontSize: 12,
  fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center',
}

function StepHead({ n, title, hint }: { n: number; title: string; hint: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
      <span style={step}>{n}</span>
      <span style={{ fontWeight: 600, fontSize: 14 }}>{title}</span>
      <span style={{ fontSize: 12, color: c.muted }}>{hint}</span>
    </div>
  )
}

function StatusPicker({ value, ai, disabled, onToggle }: { value: NeedsAction[]; ai: NeedsAction[]; disabled: boolean; onToggle: (s: NeedsAction) => void }) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      {STATUS_ORDER.map((s) => {
        const on = value.includes(s)
        const pair = STATUS_COLORS[s]
        return (
          <label key={s} style={{
            display: 'inline-flex', alignItems: 'center', gap: 7, minHeight: 36, padding: '0 12px', borderRadius: 999,
            border: `1px solid ${on ? pair.fg : c.border}`, background: on ? pair.bg : c.surface, color: on ? pair.fg : c.muted,
            fontSize: 13, fontWeight: 600, cursor: disabled ? 'default' : 'pointer', opacity: disabled && !on ? 0.6 : 1,
          }}>
            <input type="checkbox" checked={on} disabled={disabled} onChange={() => onToggle(s)}
              style={{ accentColor: pair.fg, width: 16, height: 16, margin: 0 }} />
            {s}
            {ai.includes(s) && <Chip>AI</Chip>}
          </label>
        )
      })}
    </div>
  )
}

const inputStyle: CSSProperties = { fontSize: 13 }

function ActionBlock({ a, disabled, onChange, onRemove }: { a: ActionEditVM; disabled: boolean; onChange: (p: ActionPatch) => void; onRemove: () => void }) {
  const othersMissing = a.dueType === 'Others' && !(a.dueOther ?? '').trim()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 8, borderRadius: 10, border: `1px solid ${c.border}`, background: c.surface, ...(a.highlighted ? HIGHLIGHT_STYLE : {}) }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Input value={a.description} disabled={disabled} aria-label="Action" style={{ ...inputStyle, flex: 1, background: c.surface2 }}
          onChange={(e) => onChange({ description: e.target.value })} status={a.description.trim() ? undefined : 'error'} />
        <Tooltip title={`${a.actionType}${a.ownerRole ? ` · owner ${a.ownerRole}` : ''}${a.basis ? ` · basis ${a.basis}` : ''}`}>
          <span>{a.setBy === 'ai' ? <Chip>AI</Chip> : <Chip tone="you">You</Chip>}</span>
        </Tooltip>
        {a.templated && <Chip>template</Chip>}
        <Button icon={<MinusOutlined />} aria-label="Remove action" disabled={disabled} onClick={onRemove} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <Select size="small" value={a.priority} disabled={disabled} aria-label="Priority" style={{ width: 64 }}
          onChange={(v) => onChange({ priority: v })} options={[1, 2, 3, 4, 5].map((p) => ({ value: p, label: `P${p}` }))} />
        <span style={{ fontSize: 11, color: c.muted }}>{a.aiPriority != null ? `AI: P${a.aiPriority}` : 'set by you'}</span>
        <span style={{ fontSize: 12, color: c.muted, marginLeft: 8 }}>Due</span>
        <input type="date" value={a.dueDate ?? ''} disabled={disabled} aria-label="Due date"
          onChange={(e) => onChange({ dueDate: e.target.value || null })}
          style={{ minHeight: 26, border: `1px solid ${c.border}`, background: c.surface, color: c.text, borderRadius: 6, padding: '0 8px', fontSize: 13, fontFamily: 'inherit' }} />
        <Tooltip title="What the due date is about">
          <Select<DueType> size="small" value={a.dueType} disabled={disabled} aria-label="What the due date is about" style={{ width: 112 }}
            onChange={(v) => onChange({ dueType: v, ...(v === 'Others' ? { dueOther: '' } : {}) })} options={DUE_TYPES.map((d) => ({ value: d, label: d }))} />
        </Tooltip>
        {a.dueType === 'Others' && (
          <Input size="small" value={a.dueOther === a.actionType ? '' : a.dueOther ?? ''} disabled={disabled} placeholder="about what?" aria-label="What the due date is about"
            style={{ width: 140 }} status={othersMissing ? 'error' : undefined} onChange={(e) => onChange({ dueOther: e.target.value })} />
        )}
      </div>
      {othersMissing && <span style={{ fontSize: 12, color: c.red }}>Say what the due date is about</span>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, color: STATUS_COLORS['Approval Required'].fg }}>
          <input type="checkbox" checked={a.needsApproval} disabled={disabled} onChange={(e) => onChange({ needsApproval: e.target.checked })}
            style={{ accentColor: STATUS_COLORS['Approval Required'].fg, width: 16, height: 16, margin: 0 }} />
          Needs approval
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 500, color: STATUS_COLORS['Waiting for Reply'].fg }}>
          <input type="checkbox" checked={a.awaitingReply} disabled={disabled} onChange={(e) => onChange({ awaitingReply: e.target.checked })}
            style={{ accentColor: STATUS_COLORS['Waiting for Reply'].fg, width: 16, height: 16, margin: 0 }} />
          Waiting for reply
        </label>
      </div>
    </div>
  )
}

function AddAction({ actionTypes, disabled, onAdd }: { actionTypes: string[]; disabled: boolean; onAdd: (a: ActionEditVM) => void }) {
  const [text, setText] = useState('')
  const add = () => {
    const t = text.trim()
    if (!t) return
    const type = actionTypes.find((x) => x.toLowerCase() === t.toLowerCase())
    onAdd({
      rank: 0, actionType: type ?? 'Other', description: t, ownerRole: '', basis: '', templated: false,
      priority: 3, aiPriority: null, dueType: 'Others', dueOther: type ?? t.slice(0, 40), dueDate: null,
      setBy: 'officer', highlighted: isHighlighted(3), needsApproval: false, awaitingReply: false,
    })
    setText('')
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <input list="std-actions" value={text} disabled={disabled} placeholder="Type an action, or pick one from the list" aria-label="Add action"
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && add()}
        style={{ flex: 1, minWidth: 0, minHeight: 34, boxSizing: 'border-box', border: `1px dashed ${c.border}`, background: c.surface, color: c.text, borderRadius: 8, padding: '0 10px', fontSize: 13, fontFamily: 'inherit' }} />
      <datalist id="std-actions">
        {actionTypes.map((t) => <option key={t} value={t} />)}
      </datalist>
      <Chip tone="you">You</Chip>
      <Button icon={<PlusOutlined />} aria-label="Add action" disabled={disabled || !text.trim()} onClick={add} />
    </div>
  )
}

/** F07: the side-by-side is shown only when an existing task changes; a new task needs one line. */
function TaskCompare({ p }: { p: ProposalVM }) {
  const t = p.taskCompare
  if (t.kind !== 'update' || t.changes.length === 0) return null
  return (
    <table style={{ fontSize: 12, borderCollapse: 'collapse', width: '100%', marginBottom: 6 }}>
      <thead>
        <tr style={{ color: c.muted, textAlign: 'left' }}>
          <th style={{ fontWeight: 500, padding: '2px 6px 2px 0' }}>Field</th>
          <th style={{ fontWeight: 500, padding: '2px 6px' }}>Existing task</th>
          <th style={{ fontWeight: 500, padding: '2px 6px' }}>After Confirm</th>
        </tr>
      </thead>
      <tbody>
        {t.changes.map((ch) => (
          <tr key={ch.field} style={{ borderTop: `1px solid ${c.border}` }}>
            <td style={{ padding: '4px 6px 4px 0', color: c.muted }}>{ch.field}</td>
            <td style={{ padding: '4px 6px', textDecoration: 'line-through', color: c.muted }}>{ch.old}</td>
            <td style={{ padding: '4px 6px', background: c.amberBg, color: c.text, fontWeight: 600 }}>{ch.new}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export interface ReviewPanelProps {
  proposal: ProposalVM
  statuses: NeedsAction[]
  actions: ActionEditVM[]
  edits: Record<string, string>
  editing: boolean
  submitting: boolean
  canApprove: boolean
  actionTypes: string[]
  onToggleStatus: (s: NeedsAction) => void
  onEditAction: (i: number, p: ActionPatch) => void
  onRemoveAction: (i: number) => void
  onAddAction: (a: ActionEditVM) => void
  onEditField: (name: string, value: string) => void
  onCancelEdit: () => void
  onApprove: () => void
  onReject: () => void
  compact?: boolean
}

const RESULT: Record<string, { text: string; pair: { fg: string; bg: string } }> = {
  applied: { text: 'Confirmed and applied', pair: DONE },
  rejected: { text: 'Rejected', pair: { fg: c.muted, bg: c.surface2 } },
  stale: { text: 'Replaced by a newer proposal', pair: NOT_MATCHED },
  held: { text: 'Held', pair: NOT_MATCHED },
}

export function ReviewPanel(props: ReviewPanelProps) {
  const { proposal: p, statuses, actions, edits, submitting } = props
  const disabled = p.status !== 'open' || submitting
  const auto = p.lane === 'auto_apply'
  return (
    <div style={{ ...card, padding: '16px 18px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 8 }}>
        <span style={sectionLabel}>Your review</span>
        {p.status === 'open' ? <Chip>AI suggests, you decide</Chip> : <Pill pair={RESULT[p.status].pair}>{auto && p.status === 'applied' ? 'Report applied automatically' : RESULT[p.status].text}</Pill>}
      </div>
      {p.incomplete && <Alert type="warning" showIcon style={{ marginBottom: 10 }} message="Suggestion is rule-based only (a model step did not answer)." />}
      {p.status === 'stale' && <Alert type="info" showIcon style={{ marginBottom: 10 }} message="Replaced by a newer proposal." />}
      {p.status === 'applied' && (
        <Alert type="info" showIcon style={{ marginBottom: 10 }}
          message={auto
            ? 'Routine report, filed automatically: its facts are already on the Vessel page. Nothing to review here.'
            : 'Already confirmed, so this review is read-only. To change the task, use Update on the Vessel page.'} />
      )}
      {p.status === 'rejected' && <Alert type="info" showIcon style={{ marginBottom: 10 }} message="Rejected: nothing was changed." />}

      <StepHead n={1} title="Status" hint={`AI suggested ${p.aiStatuses.length} · tick or untick; more than one is allowed`} />
      <StatusPicker value={statuses} ai={p.aiStatuses} disabled={disabled} onToggle={props.onToggleStatus} />
      <div style={{ fontSize: 12, color: statuses.length ? c.muted : c.red, marginTop: 6 }}>
        {statuses.length ? 'FYI - No Action cannot be combined with the others.' : 'Tick at least one status.'}
        {p.statusReason && <span style={{ color: c.muted }}> AI basis: {p.statusReason}</span>}
      </div>

      <div style={{ height: 16 }} />
      <StepHead n={2} title="Actions" hint={`AI found ${p.actions.length} · give each a priority and a due, tick approval or reply; edit, remove or add`} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {actions.length === 0 && <span style={{ fontSize: 13, color: c.muted }}>No action suggested.</span>}
        {actions.map((a, i) => (
          <ActionBlock key={`${a.rank}-${i}`} a={a} disabled={disabled} onChange={(patch) => props.onEditAction(i, patch)} onRemove={() => props.onRemoveAction(i)} />
        ))}
        {!disabled && <AddAction actionTypes={props.actionTypes} disabled={disabled} onAdd={props.onAddAction} />}
      </div>

      <div style={{ height: 16 }} />
      <StepHead n={3} title="What Confirm will do" hint="" />
      <TaskCompare p={p} />
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
        {p.confirmPreview.map((s) => <li key={s}>{s}</li>)}
      </ul>
      {p.taskCompare.flags.length > 0 && (
        <span style={{ fontSize: 12, color: c.amber, marginTop: 4 }}>Check: {p.taskCompare.flags.join(', ').replace(/_/g, ' ')}</span>
      )}

      {p.status === 'open' && (
        <>
          {p.closeWarning && (
            <label style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 14, fontSize: 12, fontWeight: 600, color: c.red }}>
              Reason for closing (required)
              <Input value={edits.reason ?? ''} onChange={(e) => props.onEditField('reason', e.target.value)} placeholder="Why is this task settled?" disabled={submitting} />
            </label>
          )}
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 14, fontSize: 12, fontWeight: 600, color: c.muted }}>
            Your note (optional)
            <Input value={edits.note ?? ''} onChange={(e) => props.onEditField('note', e.target.value)} placeholder="e.g. Charterers still dispute the next voyage" disabled={submitting} />
          </label>
          <div style={{ display: 'flex', gap: 8, paddingTop: 16, flexWrap: 'wrap' }}>
            <Button type="primary" onClick={props.onApprove} disabled={!props.canApprove} loading={submitting}>
              {props.editing ? 'Confirm with my changes' : 'Confirm'}
            </Button>
            <Button onClick={props.onReject} disabled={submitting}>Reject</Button>
            {props.editing && <Button type="link" onClick={props.onCancelEdit} disabled={submitting}>Undo my edits</Button>}
          </div>
          <div style={{ fontSize: 12, color: c.muted, marginTop: 10 }}>
            Confirmed emails update Overview, Vessel and Action. Your edits are logged as corrections to the AI.
          </div>
        </>
      )}
      {p.status !== 'open' && statuses.length > 0 && !props.compact && (
        <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap', alignItems: 'center', fontSize: 12, color: c.muted }}>
          Suggested statuses: {statuses.map((s) => <StatusTag key={s} status={s} />)}
        </div>
      )}
    </div>
  )
}
