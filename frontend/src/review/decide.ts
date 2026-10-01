// The one decision path (A07 to A10): the Email page and the chat review card (F-State-S17,
// E11-S30) both send the officer's decision through here, with the same guards and events.
import type { Dispatch } from 'react'
import { api } from '../api/client'
import { canApprove, type ProposalCtx, type UiEvent, type UiState } from '../state/reducer'
import { buildDecision, type ProposalVM } from '../vm/viewModels'

export const CONFLICT_TEXT = 'This item changed meanwhile. Showing the current proposal.'
export const SAVE_FAILED = 'Could not save, nothing was changed'

export type DecideOutcome = 'applied' | 'rejected' | 'conflict' | 'failed' | 'refused'

export async function decide(
  kind: 'approve' | 'reject',
  proposal: ProposalVM,
  state: UiState,
  ctx: ProposalCtx,
  dispatch: Dispatch<UiEvent>,
  now: string,
): Promise<{ outcome: DecideOutcome; undoToken: string | null }> {
  const allowed =
    kind === 'approve' ? canApprove(state, ctx) : ctx.open && (state.phase === 'EMAIL_OPEN' || state.phase === 'EDITING')
  if (!allowed) return { outcome: 'refused', undoToken: null }
  const editKind = kind === 'approve' && state.phase === 'EDITING' ? 'edit' : kind
  const decision = buildDecision(editKind, proposal, state.edits, state.actionEdits, state.statusEdits, now)
  dispatch({ type: kind, ctx })
  const r = await api.decide(proposal.proposalId, decision)
  if (r.kind === 'error') {
    dispatch({ type: 'requestFailed', message: r.status === 422 ? r.message : SAVE_FAILED })
    return { outcome: 'failed', undoToken: null }
  }
  const { result } = r.data
  if (result.status === 'applied') {
    dispatch({ type: 'applied', undoToken: result.undo_token, message: 'Applied. Overview, Vessel and Action are updated.' })
    return { outcome: 'applied', undoToken: result.undo_token }
  }
  if (result.status === 'noop' && kind === 'reject') {
    dispatch({ type: 'rejectedDone' })
    return { outcome: 'rejected', undoToken: null }
  }
  if (result.status === 'conflict' || result.status === 'noop') {
    dispatch({ type: 'conflict', message: CONFLICT_TEXT })
    dispatch({ type: 'proposalRefreshed' })
    return { outcome: 'conflict', undoToken: null }
  }
  dispatch({ type: 'requestFailed', message: SAVE_FAILED })
  return { outcome: 'failed', undoToken: null }
}
