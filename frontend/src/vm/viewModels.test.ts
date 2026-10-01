// F-VM scenarios of design_frontend.md Artifact 9.
import { describe, expect, it } from 'vitest'
import type { EmailDetail, InboxRow, Proposal } from '../api/types'
import {
  DataError,
  buildDecision,
  buildEmailDetail,
  buildInboxRows,
  buildProposal,
  factLabel,
  isHighlighted,
  segmentBody,
} from './viewModels'

const proposal = (over: Partial<Proposal> = {}): Proposal => ({
  proposal_id: 'P1',
  email_id: 'E1',
  status: 'open',
  supersedes_proposal_id: null,
  lane: { lane: 'needs_confirm', reasons: ['task_change'] },
  vessel: { vessel_code: 'VSL-02', status: 'matched', tier: 'High', score: 1, evidence: [{ quote: 'VSL-02', source: 'subject' }], candidates: [], set_by: 'rule', reason: 'subject' },
  voyage: { voyage_no: 'V202', basis: 'inferred', contract_level: 'Owner–Head', evidence: [], candidates: [], set_by: 'rule', flags: [], reason: 'date window' },
  event: { event_type: 'Redelivery Notice', tier: 'High', unsure: false, is_report: false, sources_agree: true, secondary_event_types: [], set_by: 'rule', reason: 'accepted' },
  statuses: ['Action Required'],
  priority: 4,
  fact_changes: [],
  task: { kind: 'create', task_key: 'VSL-02|V202|redelivery', target_task_id: null, target_task_version: null, changed_fields: {}, flags: [], close_warning: false, new_statuses: null, reason: '' },
  actions: {
    items: [
      { action_type: 'Check CP Terms', description: 'Check the clause', due: '2026-08-06', due_type: 'Redelivery', due_other: null, owner_role: 'Operator', decision_basis: 'CP', templated: false, for_event: 'Redelivery Notice', rank: 1, priority: 4, needs_approval: false, awaiting_reply: false },
      { action_type: 'Reply / Confirm to Counterparty', description: 'Reply', due: null, due_type: 'Others', due_other: 'survey quote', owner_role: 'Operator', decision_basis: 'CP', templated: false, for_event: 'Redelivery Notice', rank: 2, priority: 3, needs_approval: false, awaiting_reply: true },
    ],
    reason: '',
  },
  trace: [],
  incomplete: false,
  ...over,
})

const row = (over: Partial<InboxRow> = {}): InboxRow => ({
  email_id: 'E1', proposal_id: 'P1', subject: 'S', sent_time: '2026-07-30T17:54:11+08:00', sender: 'a@CPY-10.example',
  sender_role: 'Charterer', sender_party: 'CPY-10', direction: 'Inbound', vessel: 'VSL-02', voyage: 'V202',
  event_type: 'Redelivery Notice', statuses: ['Action Required'], priority: 4, review_status: 'To review',
  held_reason: null, is_report: false, ...over,
})

describe('F-VM', () => {
  it('f_vm_s01_close_proposal_preview_says_closed', () => {
    const p = buildProposal(proposal({ task: { ...proposal().task, kind: 'close_proposal', target_task_id: 'T9' } }))
    expect(p.taskCompare.kind).toBe('close_proposal')
    expect(p.confirmPreview).toContain('Task T9 will be closed.')
  })

  it('f_vm_s02_ambiguous_vessel_lists_candidates_with_tier_low', () => {
    const p = buildProposal(proposal({
      vessel: { ...proposal().vessel, vessel_code: null, status: 'ambiguous', tier: 'Medium',
                candidates: [{ vessel_code: 'VSL-01', score: 0.5 }, { vessel_code: 'VSL-02', score: 0.4 }] },
    }))
    expect(p.candidates.map((c) => c.value)).toEqual(['VSL-01', 'VSL-02'])
    expect(p.fields[0].tier).toBe('Low')
  })

  it('f_vm_s03_older_than_current_fact_is_flagged', () => {
    const p = buildProposal(proposal({
      fact_changes: [{ fact_key: 'eta:newcastle', old: '5 Aug', new: '4 Aug', event_time: '2026-07-29T08:00:00+08:00',
                       event_time_basis: 'stated', evidence: { quote: 'ETA', source: 'new_text' }, older_than_current: true }],
    }))
    expect(p.factChanges[0].olderThanCurrent).toBe(true)
    expect(p.confirmPreview[1]).toContain('kept in the history only')
  })

  it('f_vm_s04_held_email_row_has_reason', () => {
    const [r] = buildInboxRows([row({ review_status: 'Held', held_reason: 'blocked_unsanitized', vessel: null })])
    expect([r.reviewStatus, r.heldReason]).toEqual(['Held', 'Held: contains data that must be removed first'])
  })

  it('f_vm_s05_missing_optional_field_gets_default', () => {
    const [r] = buildInboxRows([row({ statuses: null, priority: null, event_type: null })])
    expect([r.statuses, r.priority, r.highlighted, r.eventType]).toEqual([[], null, false, ''])
  })

  it('f_vm_s06_missing_required_field_is_a_data_error', () => {
    expect(() => buildInboxRows([row({ review_status: undefined as never })])).toThrow(DataError)
    expect(() => buildEmailDetail({ email: null } as unknown as EmailDetail)).toThrow(DataError)
  })

  it('f_vm_s08_priorities_3_4_5_highlight_false_true_true', () => {
    expect([3, 4, 5].map(isHighlighted)).toEqual([false, true, true])
  })

  it('f_vm_s09_inbox_row_priority_4_is_highlighted', () => {
    const [r] = buildInboxRows([row({ priority: 4 })])
    expect([r.priority, r.highlighted]).toEqual([4, true])
  })

  it('f_vm_s11_decision_carries_every_action_untouched_keep_ai', () => {
    const p = buildProposal(proposal())
    const edited = [{ ...p.actions[0], priority: 5, setBy: 'officer' as const }, p.actions[1]]
    const d = buildDecision('edit', p, {}, edited, null, '2026-07-30T18:00:00+08:00')
    expect(d.actions?.map((a) => [a.priority, a.set_by, a.due_type, a.due_other])).toEqual([
      [5, 'officer', 'Redelivery', null],
      [3, 'ai', 'Others', 'survey quote'],
    ])
    expect(buildDecision('approve', p, {}, null, null, 'x').actions).toHaveLength(2)
  })

  it('f_render_s04_segments_only_mark_found_quotes', () => {
    const p = buildProposal(proposal({
      voyage: { ...proposal().voyage, evidence: [{ quote: 'redeliver at Newcastle', source: 'new_text' }] },
    }))
    const segs = segmentBody('Charterers will REDELIVER AT NEWCASTLE on 6 Aug.', p.fields)
    expect(segs.filter((x) => x.highlightKey).map((x) => [x.highlightKey, x.text])).toEqual([
      ['voyage', 'REDELIVER AT NEWCASTLE'],
    ])
    expect(segs.map((x) => x.text).join('')).toBe('Charterers will REDELIVER AT NEWCASTLE on 6 Aug.')
  })

  it('fact_label_reads_keys', () => {
    expect([factLabel('eta:newcastle'), factLabel('nor:dampier:2')]).toEqual(['ETA Newcastle', 'NOR Dampier #2'])
    expect(['eta:unknown', 'bunker_rob:vlsfo', 'sailed:dampier_p_s', 'nor:unknown:2', 'redelivery_time:V201', 'cargo_loaded_mt:unknown'].map(factLabel))
      .toEqual(['ETA', 'Bunker ROB VLSFO', 'Sailed Dampier P/S', 'NOR #2', 'Redelivery time V201', 'Cargo loaded (MT)'])
  })
})
