// Review card inside the chat (F21, U3): the same review as the Email page (status ticks, action
// list with priority, due and ticks), driven by the same reducer and guards, confirmed through the
// same decision call (F-State-S17, E11-S30). After Confirm, a confirmed line with Undo.
import { useEffect, useMemo, useReducer, useState } from 'react'
import { Alert, Button, Spin } from 'antd'
import { CheckCircleFilled } from '@ant-design/icons'
import { api } from '../../api/client'
import { decide, CONFLICT_TEXT } from '../../review/decide'
import { canApprove, initialState, reduce, type ProposalCtx } from '../../state/reducer'
import { c } from '../../theme'
import { buildEmailDetail, type EmailDetailVM } from '../../vm/viewModels'
import { ReviewPanel } from '../email/ReviewPanel'

export function ChatReviewCard({ emailId, now, actionTypes, onOpenEmail, onChanged }: {
  emailId: string
  now: string
  actionTypes: string[]
  onOpenEmail: () => void
  onChanged: () => void
}) {
  const [state, dispatch] = useReducer(reduce, { ...initialState, phase: 'EMAIL_OPEN', selectedEmailId: emailId })
  const [detail, setDetail] = useState<EmailDetailVM | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmed, setConfirmed] = useState<{ text: string; undoToken: string | null } | null>(null)
  const [undone, setUndone] = useState<string | null>(null)

  const load = async () => {
    const r = await api.email(emailId)
    if (r.kind === 'error') return setError(r.message)
    try {
      setDetail(buildEmailDetail(r.data))
    } catch {
      setError('Unexpected data from the server')
    }
  }
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emailId])

  const proposal = detail?.proposal ?? null
  const ctx: ProposalCtx = useMemo(
    () => ({ open: proposal?.status === 'open', closeWarning: proposal?.closeWarning ?? false, actions: proposal?.actions ?? [], statuses: proposal?.statuses ?? [] }),
    [proposal],
  )

  if (error) return <Alert type="warning" showIcon message="Could not load this review" description={error} />
  if (!detail || !proposal) return <Spin />

  const submit = async (kind: 'approve' | 'reject') => {
    const actions = state.actionEdits ?? proposal.actions
    const { outcome, undoToken } = await decide(kind, proposal, state, ctx, dispatch, now)
    if (outcome === 'applied') {
      const what = { create: 'new task created', update: `task ${proposal.taskCompare.taskId} updated`, close_proposal: `task ${proposal.taskCompare.taskId} closed`, none: 'email marked reviewed' }[proposal.taskCompare.kind]
      setConfirmed({ text: `Confirmed by you · ${what} (${actions.length} action${actions.length === 1 ? '' : 's'})`, undoToken })
    }
    if (outcome === 'rejected') setConfirmed({ text: 'Rejected by you', undoToken: null })
    if (outcome === 'conflict') setUndone(CONFLICT_TEXT)
    if (outcome !== 'refused' && outcome !== 'failed') {
      await load()
      onChanged()
    }
  }

  const undo = async () => {
    if (!confirmed?.undoToken) return
    const r = await api.undo(confirmed.undoToken)
    const ok = r.kind === 'ok' && r.data.status === 'applied'
    setUndone(ok ? 'Undone.' : r.kind === 'ok' && r.data.reason === 'later_change_exists' ? 'A later change exists, so this cannot be undone' : 'Could not undo')
    if (ok) setConfirmed({ ...confirmed, undoToken: null })
    onChanged()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <ReviewPanel
        compact
        proposal={proposal}
        statuses={state.statusEdits ?? proposal.statuses}
        actions={state.actionEdits ?? proposal.actions}
        edits={state.edits}
        editing={state.phase === 'EDITING'}
        submitting={state.phase === 'SUBMITTING'}
        canApprove={canApprove(state, ctx)}
        actionTypes={actionTypes}
        onToggleStatus={(s) => dispatch({ type: 'toggleStatus', status: s, ctx })}
        onEditAction={(i, patch) => dispatch({ type: 'editAction', index: i, patch, ctx })}
        onRemoveAction={(i) => dispatch({ type: 'removeAction', index: i, ctx })}
        onAddAction={(a) => dispatch({ type: 'addAction', action: a, ctx })}
        onEditField={(name, value) => dispatch({ type: 'editField', name, value, ctx })}
        onCancelEdit={() => dispatch({ type: 'cancelEdit' })}
        onApprove={() => submit('approve')}
        onReject={() => submit('reject')}
      />
      {state.phase === 'ERROR' && <Alert type="error" showIcon message={state.error?.message} action={<Button size="small" onClick={() => dispatch({ type: 'retry' })}>OK</Button>} />}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
        <Button type="link" style={{ padding: 0 }} onClick={onOpenEmail}>Open full review on the Email page →</Button>
        {!confirmed && <span style={{ fontSize: 12, color: c.muted }}>Nothing is saved until you confirm.</span>}
      </div>
      {confirmed && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 8, background: c.greenBg, color: c.green, fontSize: 13, fontWeight: 500 }}>
          <CheckCircleFilled />
          <span style={{ flexGrow: 1 }}>{confirmed.text}</span>
          {confirmed.undoToken && <Button size="small" onClick={undo}>Undo</Button>}
        </div>
      )}
      {undone && <span style={{ fontSize: 12, color: c.muted }}>{undone}</span>}
    </div>
  )
}
