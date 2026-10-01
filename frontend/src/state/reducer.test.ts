// F-State scenarios of design_frontend.md Artifact 9.
import { describe, expect, it } from 'vitest'
import type { ActionEditVM } from '../vm/viewModels'
import { initialState, reduce, type ProposalCtx, type UiEvent, type UiState } from './reducer'

const action = (over: Partial<ActionEditVM> = {}): ActionEditVM => ({
  rank: 1,
  actionType: 'Check CP Terms',
  description: 'Check the redelivery clause',
  ownerRole: 'Operator (internal)',
  basis: 'Charter Party',
  templated: false,
  priority: 3,
  aiPriority: 3,
  dueType: 'Redelivery',
  dueOther: null,
  dueDate: '2026-08-06',
  setBy: 'ai',
  highlighted: false,
  needsApproval: false,
  awaitingReply: false,
  ...over,
})

const ctx = (over: Partial<ProposalCtx> = {}): ProposalCtx => ({
  open: true,
  closeWarning: false,
  actions: [action()],
  statuses: ['Action Required'],
  ...over,
})

const open: UiState = { ...initialState, phase: 'EMAIL_OPEN', selectedEmailId: 'E1' }
const run = (s: UiState, ...events: UiEvent[]) => events.reduce(reduce, s)

describe('F-State', () => {
  it('f_state_s01_data_loaded_in_loading_is_ready', () => {
    expect(reduce(initialState, { type: 'dataLoaded' }).phase).toBe('READY')
  })

  it('f_state_s02_select_email_in_ready_opens_it', () => {
    const s = run({ ...initialState, phase: 'READY' }, { type: 'selectEmail', id: 'E7' })
    expect([s.phase, s.selectedEmailId]).toEqual(['EMAIL_OPEN', 'E7'])
  })

  it('f_state_s03_approve_when_applied_is_unchanged', () => {
    expect(reduce(open, { type: 'approve', ctx: ctx({ open: false }) })).toBe(open)
  })

  it('f_state_s04_approve_then_applied_shows_toast_with_undo', () => {
    const s = run(open, { type: 'approve', ctx: ctx() })
    expect(s.phase).toBe('SUBMITTING')
    const done = reduce(s, { type: 'applied', undoToken: 'tok', message: 'Applied' })
    expect([done.phase, done.toast?.kind, done.toast?.undoToken]).toEqual(['EMAIL_OPEN', 'applied', 'tok'])
  })

  it('f_state_s05_approve_then_conflict_then_refreshed', () => {
    const s = run(open, { type: 'approve', ctx: ctx() }, { type: 'conflict', message: 'changed' })
    expect([s.phase, s.error?.severity]).toEqual(['CONFLICT', 'WARN'])
    const back = reduce(s, { type: 'proposalRefreshed' })
    expect([back.phase, back.error]).toEqual(['EMAIL_OPEN', null])
  })

  it('f_state_s06_edit_field_then_cancel_clears_edits', () => {
    const s = run(open, { type: 'editField', name: 'note', value: 'x', ctx: ctx() })
    expect(s.phase).toBe('EDITING')
    const back = reduce(s, { type: 'cancelEdit' })
    expect([back.phase, back.edits, back.actionEdits]).toEqual(['EMAIL_OPEN', {}, null])
  })

  it('f_state_s07_approve_from_editing_with_no_edits_is_unchanged', () => {
    const s: UiState = { ...open, phase: 'EDITING', edits: { note: '  ' } }
    expect(reduce(s, { type: 'approve', ctx: ctx() })).toBe(s)
  })

  it('f_state_s08_request_failed_is_a_soft_error', () => {
    const s = run(open, { type: 'approve', ctx: ctx() }, { type: 'requestFailed', message: 'network' })
    expect([s.phase, s.error?.severity, s.selectedEmailId]).toEqual(['ERROR', 'SOFT', 'E1'])
    expect(reduce(s, { type: 'retry' }).phase).toBe('EMAIL_OPEN')
  })

  it('f_state_s09_go_to_while_submitting_is_ignored', () => {
    const s: UiState = { ...open, phase: 'SUBMITTING' }
    expect(reduce(s, { type: 'goTo', screen: 'vessel' })).toBe(s)
  })

  it('f_state_s10_unknown_event_is_unchanged', () => {
    expect(reduce(open, { type: 'nothing' } as unknown as UiEvent)).toBe(open)
  })

  it('f_state_s11_close_warning_needs_a_reason', () => {
    const c = ctx({ closeWarning: true })
    expect(reduce(open, { type: 'approve', ctx: c })).toBe(open)
    const s = run(open, { type: 'editField', name: 'reason', value: 'settled by phone', ctx: c })
    expect(reduce(s, { type: 'approve', ctx: c }).phase).toBe('SUBMITTING')
  })

  it('f_state_s12_edit_action_priority_5_is_officer_and_highlighted', () => {
    const s = run(open, { type: 'editAction', index: 0, patch: { priority: 5 }, ctx: ctx() })
    expect(s.phase).toBe('EDITING')
    expect(s.actionEdits?.[0]).toMatchObject({ priority: 5, setBy: 'officer', highlighted: true })
  })

  it('f_state_s13_approve_with_others_due_without_text_is_unchanged', () => {
    const s = run(open, { type: 'editAction', index: 0, patch: { dueType: 'Others', dueOther: '' }, ctx: ctx() })
    expect(reduce(s, { type: 'approve', ctx: ctx() })).toBe(s)
    const filled = reduce(s, { type: 'editAction', index: 0, patch: { dueOther: 'survey quote' }, ctx: ctx() })
    expect(reduce(filled, { type: 'approve', ctx: ctx() }).phase).toBe('SUBMITTING')
  })

  it('f_state_s14_toggle_approval_unticks_fyi', () => {
    const c = ctx({ statuses: ['FYI - No Action'] })
    const s = run(open, { type: 'toggleStatus', status: 'Approval Required', ctx: c })
    expect([s.phase, s.statusEdits]).toEqual(['EDITING', ['Approval Required']])
  })

  it('f_state_s15_toggle_fyi_leaves_only_fyi', () => {
    const c = ctx({ statuses: ['Action Required', 'Waiting for Reply'] })
    const s = run(open, { type: 'toggleStatus', status: 'FYI - No Action', ctx: c })
    expect(s.statusEdits).toEqual(['FYI - No Action'])
  })

  it('f_state_s16_approve_with_no_status_is_unchanged', () => {
    const s = run(open, { type: 'toggleStatus', status: 'Action Required', ctx: ctx() })
    expect(s.statusEdits).toEqual([])
    expect(reduce(s, { type: 'approve', ctx: ctx() })).toBe(s)
  })

  it('f_state_s17_chat_card_confirm_uses_the_same_guards', () => {
    // The chat review card dispatches the same approve event; a closed proposal is refused.
    expect(reduce(open, { type: 'approve', ctx: ctx({ open: false }) })).toBe(open)
    expect(reduce(open, { type: 'approve', ctx: ctx() }).phase).toBe('SUBMITTING')
  })

  it('f_state_undo_needs_a_token', () => {
    expect(reduce(open, { type: 'undo' })).toBe(open)
    const s = { ...open, toast: { kind: 'applied' as const, message: 'Applied', undoToken: 't' } }
    expect(reduce(s, { type: 'undo' }).phase).toBe('SUBMITTING')
  })
})

describe('Reducer v7: a chat quote travels with goTo', () => {
  it('f_state_goto_carries_the_quote_to_the_opened_email_and_other_moves_clear_it', () => {
    const from = { ...initialState, phase: 'READY' as const }
    const opened = reduce(from, { type: 'goTo', screen: 'email', emailId: 'E046', quote: 'Distance 1400nm' })
    expect(opened.highlightedQuote).toBe('Distance 1400nm')
    expect(reduce(opened, { type: 'goTo', screen: 'vessel', vesselCode: 'VSL-12' }).highlightedQuote).toBeNull()
  })
})

describe('Reducer v7.1: back to chat', () => {
  it('a page opened from the chat shows the way back; any other navigation clears it', () => {
    const from = { ...initialState, screen: 'chat' as const, phase: 'EMAIL_OPEN' as const }
    const opened = reduce(from, { type: 'goTo', screen: 'email', emailId: 'E046', fromChat: true })
    expect(opened.cameFromChat).toBe(true)
    expect(reduce(opened, { type: 'goTo', screen: 'chat' }).cameFromChat).toBe(false)
    expect(reduce(opened, { type: 'goTo', screen: 'vessel', vesselCode: 'VSL-12' }).cameFromChat).toBe(false)
  })
})
