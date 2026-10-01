// ChatVM (design_frontend.md Artifact 6, U3): chat turns with source chips, draft and review card.
import type { ChatAnswer, ChatPlaybook, ChatStep, FeedbackRequest, FeedbackTag, SourceRef } from '../api/types'
import type { Screen } from '../state/reducer'

export interface SourceVM {
  kind: SourceRef['kind']
  id: string
  label: string
  target: { screen: Screen; emailId?: string; vesselCode?: string }
}

export interface ChatTurnVM {
  role: 'user' | 'assistant'
  text: string
  sources: SourceVM[]
  draft: string | null
  reviewCard: { proposalId: string; emailId: string } | null
  failed: boolean
  model?: string | null // which model answered (v5.1 model picker)
  details?: string | null // v6: shown collapsed under the answer
  evidence?: VerifiedEvidence[] // v7: only quotes the backend found in the record
  mode?: string | null
  authority?: string | null
  steps?: ChatStep[]
  playbook?: ChatPlaybook | null
  trace?: string[]
  version?: string | null
  modelNote?: string | null // which models this answer really used
  demo?: boolean // a recorded demo answer (not a live one)
  asOf?: string // v7.1: HH:MM the answer was made; its records are a snapshot
  dataVersion?: number // v7.1: the app's data version when answered, to tell when records changed since
}

export interface VerifiedEvidence {
  claim: string
  sourceId: string
  quote: string
}

export const SUGGESTIONS = [
  'Any new email to review?',
  'What needs my attention today?',
  'Which dues are in the next 7 days?',
  'What changed across the fleet this week?',
  'Draft a reply to the latest redelivery notice',
]

const PAGE_SCREENS: Record<string, Screen> = { email: 'email', overview: 'overview', vessel: 'vessel', action: 'action' }

export function sourceTarget(s: SourceRef): SourceVM['target'] {
  if (s.kind === 'email') return { screen: 'email', emailId: s.id }
  if (s.kind === 'vessel') return { screen: 'vessel', vesselCode: s.id }
  if (s.kind === 'task') return { screen: 'action' }
  return { screen: PAGE_SCREENS[s.id] ?? 'overview' }
}

export function buildAnswerTurn(a: ChatAnswer, dataVersion = 0, at: Date = new Date()): ChatTurnVM {
  return {
    role: 'assistant',
    text: a.text,
    sources: (a.sources ?? []).map((s) => ({ kind: s.kind, id: s.id, label: s.label || s.id, target: sourceTarget(s) })),
    draft: a.draft ?? null,
    reviewCard: a.review_card && a.review_email_id ? { proposalId: a.review_card, emailId: a.review_email_id } : null,
    failed: a.llm_status === 'failed',
    model: a.llm_model ?? null,
    details: a.details ?? null,
    // a quote the verifier says does not support its claim is not shown as support
    evidence: (a.evidence ?? []).filter((e) => e.status === 'verified' && (!e.support || e.support === 'supports')).map((e) => ({ claim: e.claim, sourceId: e.source_id, quote: e.quote })),
    mode: a.execution_mode ?? null,
    authority: a.capability_authority ?? null,
    steps: a.steps ?? [],
    playbook: a.playbook ?? null,
    trace: a.reasoning_trace ?? [],
    version: a.version ?? null,
    modelNote: a.model_note ?? null,
    asOf: at.toTimeString().slice(0, 5),
    dataVersion,
  }
}

export interface AnswerPart {
  text: string
  link: { kind: 'email' | 'vessel'; id: string } | null
  n?: number // v7.1: the citation number shown for an email link
}

const LINK_ID = /\b(E\d{3}|VSL-\d{2})\b/g

/** v7: email ids and vessel codes in an answer become links. */
export function linkify(text: string): AnswerPart[] {
  const parts: AnswerPart[] = []
  let last = 0
  for (const m of text.matchAll(LINK_ID)) {
    const at = m.index ?? 0
    if (at > last) parts.push({ text: text.slice(last, at), link: null })
    parts.push({ text: m[0], link: { kind: m[0].startsWith('E') ? 'email' : 'vessel', id: m[0] } })
    last = at + m[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), link: null })
  return parts
}

/** v7.1: email ids become numbers [1], [2] by first appearance (a repeated id keeps its number), as in a
 * paper; `[E054]` becomes `[1]`, not `[[1]]`. Vessel codes stay links. `cited` lists the email ids in number order.
 * `cited` carries on from the earlier part (the answer, then its basis share one numbering). */
export function citeParts(text: string, cited: string[] = []): { parts: AnswerPart[]; cited: string[] } {
  const parts = linkify(text)
  cited = [...cited]
  parts.forEach((p, i) => {
    if (p.link?.kind !== 'email') return
    let at = cited.indexOf(p.link.id)
    if (at < 0) at = cited.push(p.link.id) - 1
    p.n = at + 1
    p.text = `[${at + 1}]`
    const prev = parts[i - 1]
    const next = parts[i + 1]
    if (prev && next && !prev.link && !next.link && prev.text.endsWith('[') && next.text.startsWith(']')) {
      prev.text = prev.text.slice(0, -1)
      next.text = next.text.slice(1)
    }
  })
  return { parts, cited }
}

export interface ReferenceVM {
  n: number | null // null: not numbered (a task or page)
  kind: SourceRef['kind']
  id: string
  label: string
  target: SourceVM['target']
}

/** v7.1: the one reference list under an answer: the emails cited in the answer or its basis, in number
 * order, and nothing else. An answer that cites no email in words (the sources came from a tool) lists its
 * email sources numbered. A task or page source is listed only when its id is in the text; a linked vessel is left out. */
export function buildReferences(turn: Pick<ChatTurnVM, 'sources' | 'text' | 'details'>, cited: string[]): ReferenceVM[] {
  const byId = new Map(turn.sources.map((s) => [s.id, s]))
  const emails = cited.length > 0 ? cited : turn.sources.filter((s) => s.kind === 'email').map((s) => s.id)
  const out: ReferenceVM[] = emails.map((id, i) => ({
    n: i + 1, kind: 'email', id, label: byId.get(id)?.label ?? id, target: { screen: 'email', emailId: id },
  }))
  const body = `${turn.text}\n${turn.details ?? ''}`
  for (const s of turn.sources) {
    if (s.kind === 'email' || s.kind === 'vessel' || !body.includes(s.id)) continue
    out.push({ n: null, kind: s.kind, id: s.id, label: s.label, target: s.target })
  }
  return out
}

/** The first backend-verified quote for an email id, for the hover text and the highlight. */
export const evidenceFor = (turn: Pick<ChatTurnVM, 'evidence'>, emailId: string): VerifiedEvidence | undefined =>
  turn.evidence?.find((e) => e.sourceId === emailId)

/** The body of POST /api/chat/feedback for one answer. History is the turns before the question (at most 4). */
export function feedbackBody(turn: ChatTurnVM, question: string, history: { role: 'user' | 'assistant'; text: string }[],
  thumbs: 'up' | 'down', tag: FeedbackTag | null, comment: string | null): FeedbackRequest {
  return {
    question: question.slice(0, 1000),
    history: history.slice(-4).map((h) => ({ role: h.role, text: h.text.slice(0, 2000) })),
    answer: {
      text: turn.text.slice(0, 8000), details: turn.details?.slice(0, 8000) ?? null, sources: turn.sources.map((s) => s.id).slice(0, 12),
      trace: (turn.trace ?? []).slice(0, 24), version: turn.version ?? null, model: turn.model ?? null,
      execution_mode: turn.mode ?? null, playbook: turn.playbook?.id ?? null,
    },
    thumbs, tag, comment,
  }
}

/** The recorded demo conversation as turns: each question, then its recorded answer (design 7.1, demo records). */
export function demoTurns(items: { question: string; answer: ChatAnswer; recorded_at?: string }[]): ChatTurnVM[] {
  return items.flatMap((i) => [userTurn(i.question), { ...buildAnswerTurn(i.answer, 0, i.recorded_at ? new Date(i.recorded_at) : new Date()), demo: true }])
}

export const userTurn = (text: string): ChatTurnVM => ({ role: 'user', text, sources: [], draft: null, reviewCard: null, failed: false })

/** The last 10 turns sent back as history (ChatRequest). */
export function historyOf(turns: ChatTurnVM[]): { role: 'user' | 'assistant'; text: string }[] {
  // v6: an answer's details go back too, so a follow-up ("too long", "why") can use them
  return turns.slice(-10).map((t) => ({
    role: t.role,
    text: [t.text, t.draft, t.details].filter(Boolean).join('\n').slice(0, 7000),
  }))
}
