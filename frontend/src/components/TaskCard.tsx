// A confirmed task as a card (Action page columns, Vessel page open items): title, priority badge,
// statuses, action types, due, overdue mark; priority 4 and 5 shaded.
import type { ReactNode } from 'react'
import { WarningFilled } from '@ant-design/icons'
import { HIGHLIGHT_STYLE, c } from '../theme'
import type { TaskVM } from '../vm/pages'
import { Chip, PriorityBadge, StatusTag } from './Tags'

export function TaskCard({ task, footer, showVessel = true }: { task: TaskVM; footer?: ReactNode; showVessel?: boolean }) {
  return (
    <div style={{
      background: c.surface, border: `1px solid ${c.border}`, borderRadius: 10, padding: '12px 14px',
      display: 'flex', flexDirection: 'column', gap: 6, ...(task.highlighted ? HIGHLIGHT_STYLE : {}),
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ fontWeight: 600, fontSize: 14, overflowWrap: 'anywhere' }}>{task.title}</div>
        <PriorityBadge priority={task.priority} />
      </div>
      <div style={{ fontSize: 12, color: c.muted }}>
        {[showVessel ? task.vesselCode : null, task.voyageNo, task.taskId].filter(Boolean).join(' · ')}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {task.statuses.map((s) => <StatusTag key={s} status={s} />)}
      </div>
      {task.actionTypes.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {task.actionTypes.map((a) => <Chip key={a}>{a}</Chip>)}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap', fontSize: 12 }}>
        <span style={{ color: task.overdue ? c.red : c.muted, fontWeight: task.overdue ? 600 : 400 }}>
          {task.overdue && <WarningFilled style={{ marginRight: 4 }} />}
          {task.dueLabel ? `Due · ${task.dueLabel}` : 'No due set'}
          {task.overdue && ' · overdue'}
        </span>
        {footer}
      </div>
    </div>
  )
}
