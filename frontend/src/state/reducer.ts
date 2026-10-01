// F-State f_state_reduce (design_frontend.md Artifacts 1 to 3): the next UI state from an event
// and its guard. An unknown event or a failed guard leaves the state unchanged (same object),
// with no error. Events that need facts about the proposal carry them (ctx), so the reducer
// reads no server data.
import type { NeedsAction } from '../api/types'
import type { ActionEditVM, InboxFilter } from '../vm/viewModels'
import { isHighlighted } from '../vm/viewModels'

export type Screen = 'chat' | 'email' | 'overview' | 'vessel' | 'action'
export type Phase = 'LOADING' | 'READY' | 'EMAIL_OPEN' | 'EDITING' | 'SUBMITTING' | 'CONFLICT' | 'ERROR'
export type Severity = 'HARD' | 'SOFT' | 'WARN'

export interface Toast {
  kind: 'applied' | 'rejected' | 'undone' | 'info' | 'error'
  message: string
  undoToken: string | null
}

export interface UiState {
  screen: Screen
  phase: Phase
  filter: InboxFilter
  selectedEmailId: string | null
  selectedVesselCode: string | null
  vesselStatusFilter: NeedsAction | 'High priority' | null
  highlightedField: string | null
  highlightedQuote: string | null // v7: a chat answer's quote, marked in the opened email
  cameFromChat: boolean // v7.1: the page was opened from a chat answer, so it shows "Back to chat"
  explainOpenFor: string | null
  edits: Record<string, string>
  actionEdits: ActionEditVM[] | null
  statusEdits: NeedsAction[] | null
  toast: Toast | null
  error: { severity: Severity; message: string } | null
  replayRunning: boolean
}

export const initialState: UiState = {
  screen: 'email',
  phase: 'LOADING',
  filter: 'All',
  selectedEmailId: null,
  selectedVesselCode: null,
  vesselStatusFilter: null,
  highlightedField: null,
  highlightedQuote: null,
  cameFromChat: false,
  explainOpenFor: null,
  edits: {},
  actionEdits: null,
  statusEdits: null,
  toast: null,
  error: null,
  replayRunning: false,
}

/** Facts about the open proposal that guards need. */
export interface ProposalCtx {
  open: boolean
  closeWarning: boolean
  actions: ActionEditVM[]
  statuses: NeedsAction[]
}

export type ActionPatch = Partial<
  Pick<ActionEditVM, 'description' | 'priority' | 'dueType' | 'dueOther' | 'dueDate' | 'needsApproval' | 'awaitingReply'>
>

export type UiEvent =
  | { type: 'dataLoaded' }
  | { type: 'loadFailed'; message: string }
  | { type: 'setFilter'; filter: InboxFilter }
  | { type: 'selectEmail'; id: string }
  | { type: 'closeEmail' }
  | { type: 'setHighlight'; field: string | null }
  | { type: 'toggleExplain'; field: string }
  | { type: 'editField'; name: string; value: string; ctx: ProposalCtx }
  | { type: 'cancelEdit' }
  | { type: 'editAction'; index: number; patch: ActionPatch; ctx: ProposalCtx }
  | { type: 'addAction'; action: ActionEditVM; ctx: ProposalCtx }
  | { type: 'removeAction'; index: number; ctx: ProposalCtx }
  | { type: 'toggleStatus'; status: NeedsAction; ctx: ProposalCtx }
  | { type: 'approve'; ctx: ProposalCtx }
  | { type: 'reject'; ctx: ProposalCtx }
  | { type: 'rerun'; ctx: ProposalCtx }
  | { type: 'applied'; undoToken: string | null; message: string }
  | { type: 'rejectedDone' }
  | { type: 'newProposal' }
  | { type: 'conflict'; message: string }
  | { type: 'proposalRefreshed' }
  | { type: 'requestFailed'; message: string }
  | { type: 'retry' }
  | { type: 'goTo'; screen: Screen; vesselCode?: string | null; emailId?: string | null; vesselFilter?: NeedsAction | 'High priority' | null; quote?: string | null; fromChat?: boolean }
  | { type: 'setVesselFilter'; filter: NeedsAction | 'High priority' | null }
  | { type: 'undo' }
  | { type: 'undone'; toast: Toast }
  | { type: 'dismissToast' }
  | { type: 'notify'; toast: Toast }
  | { type: 'setReplay'; running: boolean }

const CLEAN = { edits: {}, actionEdits: null, statusEdits: null } as const

const reviewPhase = (s: UiState): Phase => (s.selectedEmailId ? 'EMAIL_OPEN' : 'READY')
const canEdit = (s: UiState, ctx: ProposalCtx) =>
  ctx.open && (s.phase === 'EMAIL_OPEN' || s.phase === 'EDITING')

function hasEdits(s: UiState): boolean {
  return (
    Object.values(s.edits).some((v) => v.trim() !== '') || s.actionEdits !== null || s.statusEdits !== null
  )
}

/** Guard of approve (Artifact 3, F-State-S03, S07, S11, S13, S16). */
export function canApprove(s: UiState, ctx: ProposalCtx): boolean {
  if (!ctx.open) return false
  if (s.phase !== 'EMAIL_OPEN' && s.phase !== 'EDITING') return false
  if (s.phase === 'EDITING' && !hasEdits(s)) return false
  if (ctx.closeWarning && !(s.edits.reason ?? '').trim()) return false
  const statuses = s.statusEdits ?? ctx.statuses
  if (statuses.length === 0) return false
  const actions = s.actionEdits ?? ctx.actions
  if (actions.some((a) => a.dueType === 'Others' && !(a.dueOther ?? '').trim())) return false
  if (actions.some((a) => !a.description.trim())) return false
  return true
}

/** U2: FYI - No Action stands alone; ticking another status unticks it. */
export function toggleStatus(current: NeedsAction[], status: NeedsAction): NeedsAction[] {
  if (current.includes(status)) return current.filter((x) => x !== status)
  if (status === 'FYI - No Action') return [status]
  return [...current.filter((x) => x !== 'FYI - No Action'), status]
}

export function reduce(s: UiState, e: UiEvent): UiState {
  switch (e.type) {
    case 'dataLoaded':
      return s.phase === 'LOADING' ? { ...s, phase: reviewPhase(s) } : s
    case 'loadFailed':
      return s.phase === 'LOADING' ? { ...s, phase: 'ERROR', error: { severity: 'HARD', message: e.message } } : s
    case 'setFilter':
      return { ...s, filter: e.filter }
    case 'selectEmail':
      if (s.phase === 'READY' || (s.phase === 'EMAIL_OPEN' && e.id !== s.selectedEmailId) || s.phase === 'EDITING') {
        return {
          ...s,
          ...CLEAN,
          phase: 'EMAIL_OPEN',
          selectedEmailId: e.id,
          highlightedField: null,
          explainOpenFor: null,
          toast: s.phase === 'READY' ? s.toast : null,
        }
      }
      return s
    case 'closeEmail':
      return s.phase === 'EMAIL_OPEN' || s.phase === 'EDITING'
        ? { ...s, ...CLEAN, phase: 'READY', selectedEmailId: null }
        : s
    case 'setHighlight':
      return { ...s, highlightedField: s.highlightedField === e.field ? null : e.field }
    case 'toggleExplain':
      return { ...s, explainOpenFor: s.explainOpenFor === e.field ? null : e.field }
    case 'editField':
      return canEdit(s, e.ctx) ? { ...s, phase: 'EDITING', edits: { ...s.edits, [e.name]: e.value } } : s
    case 'cancelEdit':
      return s.phase === 'EDITING' ? { ...s, ...CLEAN, phase: 'EMAIL_OPEN' } : s
    case 'editAction': {
      const base = s.actionEdits ?? e.ctx.actions
      if (!canEdit(s, e.ctx) || !base[e.index]) return s
      if (e.patch.priority !== undefined && !(e.patch.priority >= 1 && e.patch.priority <= 5)) return s
      const next = base.map((a, i) => {
        if (i !== e.index) return a
        const merged = { ...a, ...e.patch, setBy: 'officer' as const }
        return { ...merged, highlighted: isHighlighted(merged.priority) }
      })
      return { ...s, phase: 'EDITING', actionEdits: next }
    }
    case 'addAction': {
      if (!canEdit(s, e.ctx)) return s
      const base = s.actionEdits ?? e.ctx.actions
      return { ...s, phase: 'EDITING', actionEdits: [...base, { ...e.action, rank: base.length + 1 }] }
    }
    case 'removeAction': {
      const base = s.actionEdits ?? e.ctx.actions
      if (!canEdit(s, e.ctx) || !base[e.index]) return s
      return { ...s, phase: 'EDITING', actionEdits: base.filter((_, i) => i !== e.index) }
    }
    case 'toggleStatus': {
      if (!canEdit(s, e.ctx) || e.status === 'Close') return s
      return { ...s, phase: 'EDITING', statusEdits: toggleStatus(s.statusEdits ?? e.ctx.statuses, e.status) }
    }
    case 'approve':
      return canApprove(s, e.ctx) ? { ...s, phase: 'SUBMITTING' } : s
    case 'reject':
    case 'rerun':
      return e.ctx.open && (s.phase === 'EMAIL_OPEN' || s.phase === 'EDITING') ? { ...s, phase: 'SUBMITTING' } : s
    case 'applied':
      return s.phase === 'SUBMITTING'
        ? { ...s, ...CLEAN, phase: reviewPhase(s), toast: { kind: 'applied', message: e.message, undoToken: e.undoToken } }
        : s
    case 'rejectedDone':
      return s.phase === 'SUBMITTING'
        ? { ...s, ...CLEAN, phase: reviewPhase(s), toast: { kind: 'rejected', message: 'Rejected', undoToken: null } }
        : s
    case 'newProposal':
      return s.phase === 'SUBMITTING' ? { ...s, ...CLEAN, phase: reviewPhase(s), highlightedField: null } : s
    case 'conflict':
      return s.phase === 'SUBMITTING' ? { ...s, phase: 'CONFLICT', error: { severity: 'WARN', message: e.message } } : s
    case 'proposalRefreshed':
      return s.phase === 'CONFLICT' ? { ...s, ...CLEAN, phase: 'EMAIL_OPEN', error: null } : s
    case 'requestFailed':
      return s.phase === 'SUBMITTING' ? { ...s, phase: 'ERROR', error: { severity: 'SOFT', message: e.message } } : s
    case 'retry':
      // [AMENDMENT 2026-09-26 T3.1] back to the open email when there is one, so a SOFT error
      // does not close the email the officer is working on.
      return s.phase === 'ERROR' ? { ...s, phase: s.error?.severity === 'HARD' ? 'LOADING' : reviewPhase(s), error: null } : s
    case 'goTo':
      if (s.phase === 'SUBMITTING') return s // F-State-S09
      return {
        ...s,
        ...CLEAN,
        screen: e.screen,
        phase: 'LOADING',
        error: null,
        selectedEmailId: e.emailId !== undefined ? e.emailId : e.screen === 'email' ? s.selectedEmailId : null,
        selectedVesselCode: e.vesselCode !== undefined ? e.vesselCode : s.selectedVesselCode,
        vesselStatusFilter: e.vesselFilter ?? null,
        highlightedField: null,
        highlightedQuote: e.quote ?? null,
        cameFromChat: e.fromChat === true,
      }
    case 'undo':
      return s.toast?.undoToken && s.phase !== 'SUBMITTING' && s.phase !== 'LOADING' ? { ...s, phase: 'SUBMITTING' } : s
    case 'undone':
      return s.phase === 'SUBMITTING' ? { ...s, phase: reviewPhase(s), toast: e.toast } : s
    case 'setVesselFilter':
      return { ...s, vesselStatusFilter: s.vesselStatusFilter === e.filter ? null : e.filter }
    case 'notify':
      // a result from a page without the review flow (Vessel page Update)
      return { ...s, toast: e.toast }
    case 'dismissToast':
      return s.toast ? { ...s, toast: null } : s
    case 'setReplay':
      return { ...s, replayRunning: e.running }
    default:
      return s // F-State-S10
  }
}
