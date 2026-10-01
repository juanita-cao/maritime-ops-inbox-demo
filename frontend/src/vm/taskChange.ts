// The ManualTaskChange sent by the Vessel page Update (F18, A18): only the fields that changed.
import type { ActionChange, ManualTaskChange, NeedsAction, TaskAction } from '../api/types'
import type { TaskVM } from './pages'

export type Draft = Pick<TaskAction, 'priority' | 'due_type' | 'due_other' | 'due_date' | 'needs_approval' | 'awaiting_reply'>

export const draftOf = (a: TaskAction): Draft => ({
  priority: a.priority, due_type: a.due_type, due_other: a.due_other, due_date: a.due_date,
  needs_approval: a.needs_approval, awaiting_reply: a.awaiting_reply,
})

/** The ManualTaskChange for a task and the officer's drafts; null when nothing changed. */
export function buildChange(task: TaskVM, drafts: Record<string, Draft>, statuses: NeedsAction[], done: boolean, reason: string): ManualTaskChange | null {
  const actionChanges: ActionChange[] = []
  for (const a of task.actionItems) {
    const d = drafts[a.action_id]
    if (!d) continue
    const ch: ActionChange = { action_id: a.action_id }
    for (const k of Object.keys(d) as (keyof Draft)[]) {
      if (d[k] !== a[k]) (ch as unknown as Record<string, unknown>)[k] = d[k]
    }
    if (Object.keys(ch).length > 1) actionChanges.push(ch)
  }
  const sameStatuses = statuses.length === task.statuses.length && statuses.every((s) => task.statuses.includes(s))
  if (!done && sameStatuses && actionChanges.length === 0) return null
  return {
    task_id: task.taskId,
    expected_version: task.version,
    new_statuses: done || sameStatuses ? null : statuses,
    close: done,
    action_changes: done ? [] : actionChanges,
    reason: reason.trim() || null,
  }
}

