// Chat scenarios of design_frontend.md Artifact 9 (U3).
import { describe, expect, it } from 'vitest'
import { buildAnswerTurn, buildReferences, citeParts, demoTurns, evidenceFor, feedbackBody, historyOf, linkify, userTurn } from './chat'

describe('Chat VM', () => {
  it('f_render_s14_answer_with_two_sources_and_a_draft', () => {
    const turn = buildAnswerTurn({
      text: 'Draft reply to the redelivery notice:', draft: 'Dear PER-14, ...', review_card: null, review_email_id: null, llm_status: 'ok',
      sources: [{ kind: 'email', id: 'E010', label: 'REDEL NOTICE' }, { kind: 'vessel', id: 'VSL-02', label: 'VSL-02' }],
    })
    expect(turn.sources.map((s) => s.target)).toEqual([{ screen: 'email', emailId: 'E010' }, { screen: 'vessel', vesselCode: 'VSL-02' }])
    expect(turn.draft).toBe('Dear PER-14, ...')
  })

  it('f_vm_chat_review_card_needs_proposal_and_email', () => {
    const turn = buildAnswerTurn({ text: 'New email to review', sources: [], draft: null, review_card: 'P1', review_email_id: 'E010', llm_status: 'skipped' })
    expect(turn.reviewCard).toEqual({ proposalId: 'P1', emailId: 'E010' })
    expect(turn.failed).toBe(false)
  })

  it('f_vm_chat_history_is_the_last_10_turns', () => {
    const turns = Array.from({ length: 13 }, (_, i) => userTurn(`q${i}`))
    expect(historyOf(turns).map((t) => t.text)).toEqual(['q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'q10', 'q11', 'q12'])
  })
})

describe('Chat VM v7: clickable sources', () => {
  it('f_vm_chat_links_email_ids_and_vessel_codes_in_the_answer', () => {
    expect(linkify('ETA 8/4（E053），VSL-02 在 Newcastle。')).toEqual([
      { text: 'ETA 8/4（', link: null },
      { text: 'E053', link: { kind: 'email', id: 'E053' } },
      { text: '），', link: null },
      { text: 'VSL-02', link: { kind: 'vessel', id: 'VSL-02' } },
      { text: ' 在 Newcastle。', link: null },
    ])
    expect(linkify('no ids here')).toEqual([{ text: 'no ids here', link: null }])
    expect(linkify('V202 and E0531 are not ids').every((p) => p.link === null)).toBe(true)
  })

  it('f_vm_chat_only_verified_quotes_become_evidence', () => {
    const turn = buildAnswerTurn({
      text: '距离 1,400 nm（E046）。', sources: [], draft: null, review_card: null, review_email_id: null, llm_status: 'ok',
      evidence: [
        { claim: 'distance', source_id: 'E046', quote: 'Distance 1400nm including 80nm ECA', status: 'verified' },
        { claim: 'speed', source_id: 'E046', quote: 'made up', status: 'quote_not_found' },
      ],
    })
    expect(turn.evidence).toEqual([{ claim: 'distance', sourceId: 'E046', quote: 'Distance 1400nm including 80nm ECA' }])
    expect(evidenceFor(turn, 'E046')?.quote).toContain('1400nm')
    expect(evidenceFor(turn, 'E053')).toBeUndefined()
  })
})

describe('Chat VM v7: badge data, steps and feedback body', () => {
  const answer = {
    text: '初步建议：…', sources: [{ kind: 'email' as const, id: 'E045', label: 'E045' }], draft: null, review_card: null, review_email_id: null,
    llm_status: 'ok' as const, execution_mode: 'proposal_reasoning', capability_authority: 'supported_l2', version: 'v7', llm_model: 'gpt-4o-mini',
    playbook: { id: 'cost-allocation', title: 'Who bears a cost', status: 'draft' as const },
    steps: [{ step_id: 's1', primitive: 'Detect', text: 'Identify the cost', status: 'missing' as const, note: 'no cost named', evidence_ids: [] }],
    reasoning_trace: ['Router: 3/3 samples agree on proposal_reasoning'],
    evidence: [
      { claim: 'a', source_id: 'E045', quote: 'owner took its own discretion', status: 'verified' as const, support: 'supports' as const },
      { claim: 'b', source_id: 'E045', quote: 'a clause says so', status: 'verified' as const, support: 'insufficient' as const },
    ],
  }

  it('f_vm_chat_keeps_mode_authority_playbook_and_steps_and_hides_unsupported_quotes', () => {
    const t = buildAnswerTurn(answer)
    expect([t.mode, t.authority, t.playbook?.id, t.steps?.[0].status, t.version]).toEqual(['proposal_reasoning', 'supported_l2', 'cost-allocation', 'missing', 'v7'])
    expect(t.evidence?.map((e) => e.claim)).toEqual(['a'])
  })

  it('f_vm_chat_feedback_body_has_the_question_the_last_four_turns_and_the_trace', () => {
    const t = buildAnswerTurn(answer)
    const history = Array.from({ length: 6 }, (_, i) => userTurn(`h${i}`)).map((x) => ({ role: x.role, text: x.text }))
    const body = feedbackBody(t, 'who pays', history, 'down', 'too_long', '太长')
    expect(body.history.map((h) => h.text)).toEqual(['h2', 'h3', 'h4', 'h5'])
    expect(body).toMatchObject({ question: 'who pays', thumbs: 'down', tag: 'too_long', comment: '太长' })
    expect(body.answer).toMatchObject({ version: 'v7', model: 'gpt-4o-mini', sources: ['E045'], playbook: 'cost-allocation', execution_mode: 'proposal_reasoning' })
  })
})

describe('Chat VM: which models answered', () => {
  it('f_vm_chat_keeps_the_models_note_the_backend_sends', () => {
    const t = buildAnswerTurn({ text: 'x', sources: [], draft: null, review_card: null, review_email_id: null, llm_status: 'ok', llm_model: 'hybrid',
      model_note: 'Hybrid — gpt-4o-mini only (no reasoning model needed for this answer)' })
    expect(t.modelNote).toContain('gpt-4o-mini only')
    expect(buildAnswerTurn({ text: 'x', sources: [], draft: null, review_card: null, review_email_id: null, llm_status: 'ok' }).modelNote).toBeNull()
  })
})

describe('Chat VM v7.1: numbered citations and one reference list', () => {
  const src = (id: string, kind: 'email' | 'vessel' | 'task' = 'email') => ({ kind, id, label: id, target: { screen: 'email' as const } })
  it('numbers emails by first appearance, a repeated id keeps its number, a vessel stays a link', () => {
    const { parts, cited } = citeParts('E063 asks for a refund (E054). E063 again, VSL-02.')
    expect(cited).toEqual(['E063', 'E054'])
    expect(parts.filter((p) => p.n).map((p) => p.text)).toEqual(['[1]', '[2]', '[1]'])
    expect(parts.find((p) => p.link?.kind === 'vessel')?.text).toBe('VSL-02')
  })
  it('turns [E054] into [1], not [[1]]', () => {
    const { parts } = citeParts('Speed 13 kn [E054].')
    expect(parts.map((p) => p.text).join('')).toBe('Speed 13 kn [1].')
  })
  it('lists cited emails first, then uncited ones, tasks unnumbered, a linked vessel left out', () => {
    const turn = { text: 'See E002 and VSL-02', details: null, sources: [src('E001'), src('E002'), src('VSL-02', 'vessel'), src('T9', 'task')] }
    const refs = buildReferences(turn, citeParts(turn.text).cited)
    expect(refs.map((r) => [r.id, r.n])).toEqual([['E002', 1]]) // E001 and T9 are not cited anywhere
  })
  it('the basis continues the answer numbering, and an answer that cites nothing in words lists its email sources', () => {
    const first = citeParts('See E002.')
    const second = citeParts('E001 and E002 say so (T9).', first.cited)
    expect(second.cited).toEqual(['E002', 'E001'])
    expect(second.parts.filter((p) => p.n).map((p) => p.text)).toEqual(['[2]', '[1]'])
    const turn = { text: 'No ids here', details: null, sources: [src('E001'), src('E002'), src('T9', 'task')] }
    expect(buildReferences(turn, []).map((r) => [r.id, r.n])).toEqual([['E001', 1], ['E002', 2]])
    expect(buildReferences({ ...turn, details: 'because T9' }, ['E002']).map((r) => r.id)).toEqual(['E002', 'T9'])
  })
})

describe('Chat VM: the recorded demo conversation', () => {
  it('becomes question and answer turns in order, the answers marked as recorded', () => {
    const answer = { text: 'See E002.', sources: [{ kind: 'email' as const, id: 'E002', label: 'x' }], llm_status: 'ok' as const, draft: null, review_card: null, review_email_id: null }
    const turns = demoTurns([{ question: 'q1', answer, recorded_at: '2026-10-12T09:30:00+08:00' }, { question: 'q2', answer }])
    expect(turns.map((t) => [t.role, t.text])).toEqual([['user', 'q1'], ['assistant', 'See E002.'], ['user', 'q2'], ['assistant', 'See E002.']])
    expect(turns.filter((t) => t.role === 'assistant').every((t) => t.demo === true)).toBe(true)
  })
})
