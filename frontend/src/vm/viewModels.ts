// F-VM f_build_viewmodel (design_frontend.md Artifact 6): pure mappings from API JSON to flat
// view models. Missing optional fields get a default; a missing required field is a DataError
// (shown as "Unexpected data from the server", F-VM-S06).
import type {
  ConfirmedAction,
  Decision,
  DueType,
  EmailDetail,
  Evidence,
  InboxRow,
  NeedsAction,
  Proposal,
  ReviewStatus,
  Tier,
} from '../api/types'

export class DataError extends Error {}

/** The one shading rule of U1: priority 4 and 5 are highlighted everywhere. */
export const isHighlighted = (priority: number | null | undefined): boolean =>
  priority != null && priority >= 4

function required<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new DataError(`missing ${what}`)
  return value
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-07-30T17:54:11+08:00" to "30 Jul 17:54", in the sender's own offset (no conversion). */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(iso)
  if (!m) return iso
  const day = `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}`
  return m[4] ? `${day} ${m[4]}:${m[5]}` : day
}

/** "2026-08-06" to "6 Aug". */
export const formatDate = (iso: string | null | undefined): string => formatTime(iso)

// --- inbox ------------------------------------------------------------------------------

export interface InboxRowVM {
  emailId: string
  proposalId: string | null
  vesselCode: string | null
  voyageNo: string | null
  subject: string
  sentDate: string
  sentTime: string
  senderRole: string
  eventType: string
  statuses: NeedsAction[]
  reviewStatus: ReviewStatus
  heldReason: string | null
  isReport: boolean
  priority: number | null
  highlighted: boolean
}

const HELD_TEXT: Record<string, string> = {
  blocked_unsanitized: 'Held: contains data that must be removed first',
  store_unavailable: 'Held: will be processed when the store is back',
}

export function heldText(reason: string | null | undefined): string {
  return (reason && HELD_TEXT[reason]) || 'Held'
}

export function senderLabel(direction: string, role: string, party: string | null): string {
  if (direction === 'Outbound') return 'Sent by us'
  if (role === 'Other') return party ?? 'Unknown sender'
  return party ? `${role} (${party})` : role
}

export function buildInboxRows(rows: InboxRow[]): InboxRowVM[] {
  return rows.map((r) => ({
    emailId: required(r.email_id, 'email_id'),
    proposalId: r.proposal_id ?? null,
    vesselCode: r.vessel ?? null,
    voyageNo: r.voyage ?? null,
    subject: r.subject || '(no subject)',
    sentDate: formatTime(r.sent_time),
    sentTime: r.sent_time ?? '',
    senderRole: senderLabel(r.direction, r.sender_role ?? 'Other', r.sender_party ?? null),
    eventType: r.event_type ?? '',
    statuses: r.statuses ?? [],
    reviewStatus: required(r.review_status, 'review_status'),
    heldReason: r.review_status === 'Held' ? heldText(r.held_reason) : null,
    isReport: Boolean(r.is_report),
    priority: r.priority ?? null,
    highlighted: isHighlighted(r.priority),
  }))
}

export type InboxFilter =
  | 'All'
  | 'To review'
  | 'High priority'
  | 'Not matched'
  | Exclude<NeedsAction, 'Close'>

export const FILTERS: InboxFilter[] = [
  'All',
  'To review',
  'Action Required',
  'Approval Required',
  'Waiting for Reply',
  'FYI - No Action',
  'Not matched',
]

export function matchesFilter(row: InboxRowVM, filter: InboxFilter): boolean {
  switch (filter) {
    case 'All':
      return true
    case 'To review':
      return row.reviewStatus === 'To review'
    case 'High priority':
      return row.highlighted
    case 'Not matched':
      return row.reviewStatus === 'Not matched'
    default:
      return row.statuses.includes(filter)
  }
}

// --- email detail and proposal ------------------------------------------------------------

export interface FieldVM {
  key: string
  label: string
  value: string
  tier: Tier | null
  basisLabel: string
  evidence: Evidence | null
  setBy: 'rule' | 'officer'
}

export interface ActionEditVM {
  rank: number
  actionType: string
  description: string
  ownerRole: string
  basis: string
  templated: boolean
  priority: number
  aiPriority: number | null
  dueType: DueType
  dueOther: string | null
  dueDate: string | null
  setBy: 'ai' | 'officer'
  highlighted: boolean
  needsApproval: boolean
  awaitingReply: boolean
}

export interface CandidateVM {
  kind: 'vessel' | 'voyage'
  value: string
  label: string
  score: number | null
}

export interface TaskCompareVM {
  kind: 'create' | 'update' | 'close_proposal' | 'none'
  taskId: string | null
  taskKey: string | null
  changes: { field: string; old: string; new: string }[]
  flags: string[]
  reason: string
}

export interface FactChangeVM {
  key: string
  label: string
  old: string | null
  new: string
  eventTime: string
  olderThanCurrent: boolean
  evidence: Evidence
}

export interface ProposalVM {
  proposalId: string
  status: 'open' | 'applied' | 'rejected' | 'stale' | 'held'
  lane: 'auto_apply' | 'needs_confirm'
  laneReasons: string[]
  attachmentDependent: boolean
  closeWarning: boolean
  incomplete: boolean
  fields: FieldVM[]
  candidates: CandidateVM[]
  actions: ActionEditVM[]
  actionsReason: string
  statuses: NeedsAction[]
  aiStatuses: NeedsAction[]
  statusReason: string
  taskCompare: TaskCompareVM
  factChanges: FactChangeVM[]
  confirmPreview: string[]
  supersededBy: string | null
  eventType: string
}

export interface BodySegment {
  text: string
  highlightKey: string | null
}

export interface EmailDetailVM {
  emailId: string
  subject: string
  sender: string
  sentDate: string
  receivers: string
  attachments: string[]
  bodySegments: BodySegment[]
  quotedText: string
  proposal: ProposalVM | null
  proposalStatusLabel: string
  held: string | null
  supersededCount: number
}

const TIER_OF_BASIS: Record<string, Tier> = { stated: 'High', inferred: 'Medium', none: 'Low' }

const FACT_KIND: Record<string, string> = {
  eta: 'ETA', etb: 'ETB', etd: 'ETD', nor: 'NOR', bunker_rob: 'Bunker ROB', cargo_loaded_mt: 'Cargo loaded (MT)',
  cargo_discharged_mt: 'Cargo discharged (MT)', speed_avg: 'Average speed', redelivery_time: 'Redelivery time',
  invoice_amount: 'Invoice amount',
}
const UPPER = new Set(['fw', 'lsmgo', 'vlsfo', 'mgo', 'hfo', 'ifo', 'cnlyg'])

/** "eta:newcastle" to "ETA Newcastle"; "nor:dampier:2" to "NOR Dampier #2"; "unknown" places are left out. */
export function factLabel(key: string): string {
  const [kind, ...rest] = key.split(':')
  const parts = rest.filter((x) => x && x !== '-' && x.toLowerCase() !== 'unknown')
  const ordinal = parts.length > 0 && /^\d+$/.test(parts[parts.length - 1]) ? `#${parts.pop()}` : ''
  const place = parts
    .map((p) =>
      /[ .]/.test(p) || /^[A-Z]/.test(p)
        ? p
        : p.replace(/(^|_)p_s($|_)/g, '$1P/S$2').split('_').map((w) => (UPPER.has(w) ? w.toUpperCase() : w === 'P/S' ? w : w.charAt(0).toUpperCase() + w.slice(1))).join(' '),
    )
    .join(' ')
  const head = FACT_KIND[kind] ?? kind.charAt(0).toUpperCase() + kind.slice(1).replace(/_/g, ' ')
  return [head, place, ordinal].filter(Boolean).join(' ')
}

function stringify(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  if (Array.isArray(v)) return v.join(', ')
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function toActionEdits(p: Proposal): ActionEditVM[] {
  return (p.actions?.items ?? []).map((a) => ({
    rank: a.rank,
    actionType: a.action_type,
    description: a.description,
    ownerRole: a.owner_role ?? '',
    basis: a.decision_basis ?? '',
    templated: Boolean(a.templated),
    priority: a.priority,
    aiPriority: a.priority,
    dueType: a.due_type,
    dueOther: a.due_other ?? null,
    dueDate: a.due ?? null,
    setBy: 'ai',
    highlighted: isHighlighted(a.priority),
    needsApproval: Boolean(a.needs_approval),
    awaitingReply: Boolean(a.awaiting_reply),
  }))
}

function proposalStatus(s: string): ProposalVM['status'] {
  return s.startsWith('held') ? 'held' : (s as ProposalVM['status'])
}

export function buildProposal(p: Proposal, attachmentDependent = false): ProposalVM {
  required(p.proposal_id, 'proposal_id')
  const vessel = required(p.vessel, 'vessel')
  const voyage = required(p.voyage, 'voyage')
  const event = required(p.event, 'event')
  const task = required(p.task, 'task')
  const fields: FieldVM[] = [
    {
      key: 'vessel',
      label: 'Vessel',
      value: vessel.vessel_code ?? (vessel.status === 'ambiguous' ? 'Ambiguous' : 'Not identified'),
      tier: vessel.status === 'matched' ? vessel.tier : 'Low',
      basisLabel: vessel.reason || '',
      evidence: vessel.evidence?.[0] ?? null,
      setBy: vessel.set_by ?? 'rule',
    },
    {
      key: 'voyage',
      label: 'Voyage',
      value: voyage.voyage_no ?? 'Not identified',
      tier: TIER_OF_BASIS[voyage.basis] ?? 'Low',
      basisLabel: [voyage.basis, voyage.reason].filter(Boolean).join(': '),
      evidence: voyage.evidence?.[0] ?? null,
      setBy: voyage.set_by ?? 'rule',
    },
    {
      key: 'event',
      label: 'Event',
      value: event.event_type,
      tier: event.tier,
      basisLabel: event.reason || '',
      evidence: null,
      setBy: event.set_by ?? 'rule',
    },
  ]
  if (voyage.contract_level) {
    fields.push({
      key: 'contract',
      label: 'Contract level',
      value: voyage.contract_level,
      tier: null,
      basisLabel: 'From the charter chain of the voyage',
      evidence: null,
      setBy: 'rule',
    })
  }
  const factChanges: FactChangeVM[] = (p.fact_changes ?? []).map((f) => ({
    key: f.fact_key,
    label: factLabel(f.fact_key),
    old: f.old ?? null,
    new: f.new,
    eventTime: formatTime(f.event_time),
    olderThanCurrent: Boolean(f.older_than_current),
    evidence: f.evidence,
  }))
  for (const f of factChanges) {
    fields.push({
      key: `fact:${f.key}`,
      label: f.label,
      value: f.new,
      tier: null,
      basisLabel: f.eventTime ? `Event time ${f.eventTime}` : 'No event time',
      evidence: f.evidence,
      setBy: 'rule',
    })
  }
  const candidates: CandidateVM[] = [
    ...(vessel.status !== 'matched' ? vessel.candidates ?? [] : []).map((c) => ({
      kind: 'vessel' as const,
      value: c.vessel_code,
      label: c.vessel_code,
      score: c.score,
    })),
    ...(voyage.candidates ?? [])
      .filter((v) => v !== voyage.voyage_no)
      .map((v) => ({ kind: 'voyage' as const, value: v, label: v, score: null })),
  ]
  const changes = Object.entries(task.changed_fields ?? {}).map(([field, ch]) => ({
    field,
    old: stringify(ch.old),
    new: stringify(ch.new),
  }))
  const taskCompare: TaskCompareVM = {
    kind: task.kind,
    taskId: task.target_task_id ?? null,
    taskKey: task.task_key ?? null,
    changes,
    flags: task.flags ?? [],
    reason: task.reason ?? '',
  }
  const statusStep = (p.trace ?? []).find((t) => t.node === 'D4')
  const vm: ProposalVM = {
    proposalId: p.proposal_id,
    status: proposalStatus(p.status ?? 'open'),
    lane: p.lane?.lane ?? 'needs_confirm',
    laneReasons: p.lane?.reasons ?? [],
    attachmentDependent,
    closeWarning: Boolean(task.close_warning),
    incomplete: Boolean(p.incomplete),
    fields,
    candidates,
    actions: toActionEdits(p),
    actionsReason: p.actions?.reason ?? '',
    statuses: p.statuses ?? [],
    aiStatuses: p.statuses ?? [],
    statusReason: statusStep?.rule_or_basis ?? '',
    taskCompare,
    factChanges,
    confirmPreview: [],
    supersededBy: null,
    eventType: event.event_type,
  }
  vm.confirmPreview = previewSentences(vm)
  return vm
}

export function previewSentences(p: ProposalVM): string[] {
  const out: string[] = []
  const t = p.taskCompare
  if (t.kind === 'create') out.push('A new task will be created with the actions above.')
  if (t.kind === 'update') {
    const what = t.changes.map((c) => `${c.field} ${c.old} → ${c.new}`).join('; ')
    out.push(`Task ${t.taskId} will be updated${what ? `: ${what}` : ''}.`)
  }
  if (t.kind === 'close_proposal') out.push(`Task ${t.taskId} will be closed.`)
  for (const f of p.factChanges) {
    out.push(
      f.olderThanCurrent
        ? `${f.label} ${f.new} is older than the current value; it is kept in the history only.`
        : `${f.label} will be set to ${f.new}${f.old ? ` (was ${f.old})` : ''}.`,
    )
  }
  if (out.length === 0) out.push('Nothing changes in tasks or facts; the email is marked reviewed.')
  return out
}

/** Split the email text so each evidence quote is its own segment (first match wins). */
export function segmentBody(text: string, fields: FieldVM[]): BodySegment[] {
  const norm = text.toLowerCase()
  const ranges: { start: number; end: number; key: string }[] = []
  for (const f of fields) {
    const q = f.evidence?.quote
    if (!q || f.evidence?.source === 'subject') continue
    const at = norm.indexOf(q.toLowerCase())
    if (at < 0) continue
    const end = at + q.length
    if (ranges.some((r) => at < r.end && end > r.start)) continue
    ranges.push({ start: at, end, key: f.key })
  }
  ranges.sort((a, b) => a.start - b.start)
  const out: BodySegment[] = []
  let pos = 0
  for (const r of ranges) {
    if (r.start > pos) out.push({ text: text.slice(pos, r.start), highlightKey: null })
    out.push({ text: text.slice(r.start, r.end), highlightKey: r.key })
    pos = r.end
  }
  if (pos < text.length || out.length === 0) out.push({ text: text.slice(pos), highlightKey: null })
  return out
}

const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  open: 'To review',
  applied: 'Applied',
  rejected: 'Rejected',
  stale: 'Replaced by a newer proposal',
  held_blocked: 'Held',
  held_store_unavailable: 'Held',
}

export function buildEmailDetail(d: EmailDetail): EmailDetailVM {
  const email = required(d.email, 'email')
  const sender = d.roles?.sender
  const proposal = d.proposal ? buildProposal(d.proposal, Boolean(email.attachment_dependent)) : null
  if (proposal && d.proposal_status) proposal.status = proposalStatus(d.proposal_status)
  return {
    emailId: email.email_id,
    subject: email.subject || '(no subject)',
    sender: senderLabel(email.direction, sender?.role ?? 'Other', sender?.party_code ?? null),
    sentDate: formatTime(email.sent_time),
    receivers: (d.roles?.receivers ?? [])
      .map((r) => r.party_code ?? r.address)
      .filter((x, i, all) => all.indexOf(x) === i)
      .join(', '),
    attachments: (email.attachment_names ?? []).filter((n) => n && n !== '无'),
    bodySegments: segmentBody(email.new_text ?? '', proposal?.fields ?? []),
    quotedText: email.quoted_text ?? '',
    proposal,
    proposalStatusLabel: d.proposal_status ? PROPOSAL_STATUS_LABEL[d.proposal_status] ?? d.proposal_status : 'No proposal',
    held: d.held ? heldText(d.held.reason) : null,
    supersededCount: d.superseded?.length ?? 0,
  }
}

// --- the decision sent to the backend -----------------------------------------------------

export function toConfirmedActions(actions: ActionEditVM[]): ConfirmedAction[] {
  return actions.map((a) => ({
    action_type: a.actionType,
    description: a.description,
    priority: a.priority,
    due_type: a.dueType,
    due_other: a.dueType === 'Others' ? a.dueOther : null,
    due_date: a.dueDate || null,
    set_by: a.setBy,
    needs_approval: a.needsApproval,
    awaiting_reply: a.awaitingReply,
  }))
}

/** F-VM-S11: the Decision carries every confirmed action; untouched ones keep set_by ai. */
export function buildDecision(
  kind: 'approve' | 'edit' | 'reject',
  proposal: ProposalVM,
  edits: Record<string, string>,
  actionEdits: ActionEditVM[] | null,
  statusEdits: NeedsAction[] | null,
  decidedAt: string,
): Decision {
  const reason = [edits.reason, edits.note].map((x) => x?.trim()).filter(Boolean).join(' · ') || null
  if (kind === 'reject') {
    return { kind, actor: 'officer', edits: {}, actions: null, statuses: null, reason, decided_at: decidedAt }
  }
  return {
    kind,
    actor: 'officer',
    edits: {},
    actions: toConfirmedActions(actionEdits ?? proposal.actions),
    statuses: statusEdits ?? null,
    reason,
    decided_at: decidedAt,
  }
}
