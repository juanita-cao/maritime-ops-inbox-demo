// Update of a confirmed task (F18, A18): per action the priority, the due and the Needs approval
// and Waiting for reply ticks; Mark done closes the item. Sends a ManualTaskChange with only what
// changed; E11 applies it with the version check, history and undo.
// [AMENDMENT 2026-09-26 UI round U6, owner] the task statuses row is hidden for the demo (the
// statuses stay as they are); Done is a button; fewer words on each action row.
import { useState } from 'react'
import { Button, Input, Select, Tooltip } from 'antd'
import { DUE_TYPES, type DueType, type ManualTaskChange } from '../../api/types'
import { buildChange, draftOf, type Draft } from '../../vm/taskChange'
import { STATUS_COLORS, c } from '../../theme'
import type { TaskVM } from '../../vm/pages'

const TICKS = [
  ['needs_approval', 'Needs approval', 'Approval Required'],
  ['awaiting_reply', 'Waiting for reply', 'Waiting for Reply'],
] as const

export function UpdateTask({ task, busy, onSave, onCancel }: { task: TaskVM; busy: boolean; onSave: (c: ManualTaskChange) => void; onCancel: () => void }) {
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => Object.fromEntries(task.actionItems.map((a) => [a.action_id, draftOf(a)])))
  const patch = (id: string, p: Partial<Draft>) => setDrafts((d) => ({ ...d, [id]: { ...d[id], ...p } }))
  const change = buildChange(task, drafts, task.statuses, false, '')
  const othersMissing = Object.values(drafts).some((d) => d.due_type === 'Others' && !(d.due_other ?? '').trim())

  return (
    <div style={{ marginTop: 8, padding: 12, borderRadius: 10, background: c.surface2, border: `1px solid ${c.border}`, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {task.actionItems.map((a) => {
        const d = drafts[a.action_id]
        return (
          <div key={a.action_id} style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingBottom: 10, borderBottom: `1px solid ${c.border}` }}>
            <div style={{ fontSize: 13, fontWeight: 500 }}>{a.description}</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <Select size="small" value={d.priority} style={{ width: 64 }} aria-label="Priority"
                onChange={(v) => patch(a.action_id, { priority: v })} options={[1, 2, 3, 4, 5].map((p) => ({ value: p, label: `P${p}` }))} />
              {d.priority !== a.priority && <span style={{ fontSize: 11, color: c.muted }}>was P{a.priority}</span>}
              <span style={{ fontSize: 12, color: c.muted, marginLeft: 8 }}>Due</span>
              <input type="date" value={d.due_date ?? ''} aria-label="Due date" onChange={(e) => patch(a.action_id, { due_date: e.target.value || null })}
                style={{ minHeight: 24, border: `1px solid ${c.border}`, borderRadius: 6, padding: '0 8px', fontSize: 13, fontFamily: 'inherit', color: c.text, background: c.surface }} />
              <Tooltip title="What the due date is about">
                <Select<DueType> size="small" value={d.due_type} style={{ width: 112 }} aria-label="What the due date is about"
                  onChange={(v) => patch(a.action_id, { due_type: v, ...(v === 'Others' && a.due_type !== 'Others' ? { due_other: '' } : {}) })}
                  options={DUE_TYPES.map((x) => ({ value: x, label: x }))} />
              </Tooltip>
              {d.due_type === 'Others' && (
                <Input size="small" value={d.due_other === a.action_type ? '' : d.due_other ?? ''} placeholder="about what?" style={{ width: 140 }}
                  status={(d.due_other ?? '').trim() ? undefined : 'error'} onChange={(e) => patch(a.action_id, { due_other: e.target.value })} aria-label="What the due date is about" />
              )}
              {TICKS.map(([k, text, status]) => (
                <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 500, color: STATUS_COLORS[status].fg, marginLeft: 8 }}>
                  <input type="checkbox" checked={d[k]} onChange={(e) => patch(a.action_id, { [k]: e.target.checked })}
                    style={{ accentColor: STATUS_COLORS[status].fg, width: 15, height: 15, margin: 0 }} />
                  {text}
                </label>
              ))}
            </div>
          </div>
        )
      })}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button type="primary" disabled={!change || othersMissing} loading={busy} onClick={() => change && onSave(change)}>Save</Button>
        <Button onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button style={{ color: c.green, borderColor: c.green }} disabled={busy}
          onClick={() => { const done = buildChange(task, {}, task.statuses, true, ''); if (done) onSave(done) }}>
          Mark done
        </Button>
      </div>
    </div>
  )
}
