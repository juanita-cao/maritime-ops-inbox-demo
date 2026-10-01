// JSON shapes of the backend (backend/src/schemas.py and api.py, design_frontend.md Artifact 5
// as built in T2.21). Only the fields the frontend reads are listed.

export type NeedsAction =
  | 'Action Required'
  | 'Approval Required'
  | 'Waiting for Reply'
  | 'FYI - No Action'
  | 'Close'

export const STATUS_ORDER: NeedsAction[] = [
  'Action Required',
  'Approval Required',
  'Waiting for Reply',
  'FYI - No Action',
]

export type Tier = 'High' | 'Medium' | 'Low'
export type DueType = 'Delivery' | 'Redelivery' | 'Hire' | 'Invoice' | 'Others'
export const DUE_TYPES: DueType[] = ['Delivery', 'Redelivery', 'Hire', 'Invoice', 'Others']
export type ProposalStatus =
  | 'open'
  | 'applied'
  | 'rejected'
  | 'stale'
  | 'held_blocked'
  | 'held_store_unavailable'
export type ReviewStatus = 'To review' | 'Reviewed' | 'Not matched' | 'Held'

export interface Evidence {
  quote: string
  source: 'subject' | 'new_text' | 'quoted_text' | 'attachments' | 'kb'
}

export interface InboxRow {
  email_id: string
  proposal_id: string | null
  subject: string
  sent_time: string | null
  sender: string
  sender_role: string
  sender_party: string | null
  direction: 'Inbound' | 'Outbound'
  vessel: string | null
  voyage: string | null
  event_type: string | null
  statuses: NeedsAction[] | null
  priority: number | null
  review_status: ReviewStatus
  held_reason: string | null
  is_report: boolean
}

export interface ParsedEmail {
  email_id: string
  subject: string
  sent_time: string | null
  direction: 'Inbound' | 'Outbound'
  sender: string
  receivers: string[]
  new_text: string
  quoted_text: string
  attachment_dependent: boolean
  attachment_names: string[]
}

export interface PartyRef {
  address: string
  party_code: string | null
  role: string
}

export interface VesselMatch {
  vessel_code: string | null
  status: 'matched' | 'ambiguous' | 'none'
  tier: Tier
  score: number
  evidence: Evidence[]
  candidates: { vessel_code: string; score: number }[]
  set_by: 'rule' | 'officer'
  reason: string
}

export interface VoyageMatch {
  voyage_no: string | null
  basis: 'stated' | 'inferred' | 'none'
  contract_level: string | null
  evidence: Evidence[]
  candidates: string[]
  set_by: 'rule' | 'officer'
  flags: string[]
  reason: string
}

export interface EventDecision {
  event_type: string
  tier: Tier
  unsure: boolean
  is_report: boolean
  sources_agree: boolean
  secondary_event_types: string[]
  set_by: 'rule' | 'officer'
  reason: string
}

export interface RankedAction {
  action_type: string
  description: string
  due: string | null
  due_type: DueType
  due_other: string | null
  owner_role: string
  decision_basis: string
  templated: boolean
  for_event: string
  rank: number
  priority: number
  needs_approval: boolean
  awaiting_reply: boolean
}

export interface FieldChange {
  old: unknown
  new: unknown
}

export interface TaskDisposition {
  kind: 'create' | 'update' | 'close_proposal' | 'none'
  task_key: string | null
  target_task_id: string | null
  target_task_version: number | null
  changed_fields: Record<string, FieldChange>
  flags: string[]
  close_warning: boolean
  new_statuses: NeedsAction[] | null
  reason: string
}

export interface FactChange {
  fact_key: string
  old: string | null
  new: string
  event_time: string | null
  event_time_basis: 'stated' | 'email_sent_time' | null
  evidence: Evidence
  older_than_current: boolean
}

export interface TraceStep {
  node: string
  rule_or_basis: string
  confidence: number | null
  evidence: Evidence[]
}

export interface Proposal {
  proposal_id: string
  email_id: string
  status: ProposalStatus
  supersedes_proposal_id: string | null
  lane: { lane: 'auto_apply' | 'needs_confirm'; reasons: string[] }
  vessel: VesselMatch
  voyage: VoyageMatch
  event: EventDecision
  statuses: NeedsAction[]
  priority: number
  fact_changes: FactChange[]
  task: TaskDisposition
  actions: { items: RankedAction[]; reason: string }
  trace: TraceStep[]
  incomplete: boolean
}

export interface HeldInfo {
  reason?: string
  detail?: string
}

export interface EmailDetail {
  email: ParsedEmail
  roles: { sender: PartyRef; receivers: PartyRef[] }
  proposal: Proposal | null
  proposal_status: ProposalStatus | null
  held: HeldInfo | null
  superseded: string[]
}

export interface ConfirmedAction {
  action_type: string
  description: string
  priority: number
  due_type: DueType
  due_other: string | null
  due_date: string | null
  set_by: 'ai' | 'officer'
  needs_approval: boolean
  awaiting_reply: boolean
}

export interface Decision {
  kind: 'approve' | 'edit' | 'reject'
  actor: 'officer'
  edits: Record<string, string>
  actions: ConfirmedAction[] | null
  statuses: NeedsAction[] | null
  reason: string | null
  decided_at: string
}

export interface ApplyResult {
  status: 'applied' | 'conflict' | 'rolled_back' | 'noop'
  reason: string | null
  applied_task_id: string | null
  undo_token: string | null
  conflict_detail: string | null
}

export interface DecisionResponse {
  result: ApplyResult
  proposal: Proposal | null
}

export interface Overrides {
  vessel_code?: string | null
  voyage_no?: string | null
  event_type?: string | null
}

export interface PipelineResult {
  email_id: string
  saved: { proposal_id: string; status: ProposalStatus }
  proposal: Proposal | null
  held: { email_id: string; reason: string; detail: string } | null
  applied: ApplyResult | null
}

export interface ReviewQueue {
  items: { proposal_id: string; email_id: string; status: ProposalStatus }[]
  store_status: 'ok' | 'unavailable'
}

export interface Health {
  status: string
  llm_mode: string
  now: string
  dataset?: string // 'mock' or 'desanitized'
}

export type Taxonomy = Record<string, string[]>

export interface VesselRow {
  vessel_code: string
  voyages: string[]
  current_voyage: string | null
  counts: Record<string, number>
  high_priority: number
  voyage_details: VoyageDetail[]
}

export interface VoyageDetail {
  voyage_no: string
  status: string
  route: string
  start: string
  end: string
  facts: string
}

export interface TaskRow {
  task_id: string
  vessel: string
  voyage: string | null
  action: string
  priority: number
  due_type: DueType | null
  deadline: string | null
  overdue: boolean
  statuses: NeedsAction[]
  source_email_id: string
  task_key: string
  version: number
  actions: TaskAction[]
}

export interface TaskAction {
  action_id: string
  task_id: string
  action_type: string
  description: string
  priority: number
  due_type: DueType
  due_other: string | null
  due_date: string | null
  set_by: 'ai' | 'officer'
  source_email_id: string
  needs_approval: boolean
  awaiting_reply: boolean
}

export interface RankedTaskList {
  groups: { name: 'Action Required' | 'Approval Required' | 'Waiting for Reply'; items: TaskRow[] }[]
}

export interface DueRow {
  task_id: string
  action_id: string
  vessel: string
  voyage: string | null
  action: string
  due_type: DueType
  due_other: string | null
  due_date: string
  priority: number
  overdue: boolean
}

export interface DueList {
  items: DueRow[]
  store_status: 'ok' | 'unavailable'
}

export interface VesselView {
  vessel_code: string
  facts: { fact_key: string; value: string; event_time: string; source_email_id: string; superseded: boolean }[]
  timeline: { event_time: string; event_type: string; email_id: string; changed_fact_keys: string[] }[]
  open_tasks: TaskRow[]
  auto_applied: { email_id: string; fact_keys: string[]; applied_at: string; undo_available: boolean }[]
}

export interface ActionChange {
  action_id: string
  priority?: number
  due_type?: DueType
  due_other?: string | null
  due_date?: string | null
  needs_approval?: boolean
  awaiting_reply?: boolean
}

export interface ManualTaskChange {
  task_id: string
  expected_version: number
  new_statuses: NeedsAction[] | null
  close: boolean
  action_changes: ActionChange[]
  reason: string | null
}

export interface SourceRef {
  kind: 'email' | 'vessel' | 'task' | 'page'
  id: string
  label: string
}

export interface ChatRequest {
  question: string
  history: { role: 'user' | 'assistant'; text: string }[]
  model?: string | null // an id from GET /api/chat/models; null = the server default
}

export interface ChatModel {
  id: string
  label: string
  note: string
  fast?: string
  reasoning?: string
}

export interface ChatModels {
  default: string
  models: ChatModel[]
}

export interface ChatEvidence {
  claim: string
  source_id: string
  quote: string
  status: 'verified' | 'quote_not_found' | 'source_not_read'
  support?: 'supports' | 'contradicts' | 'unrelated' | 'insufficient' | null
}

export interface ChatStep {
  step_id: string
  primitive: string
  text: string
  status: 'done' | 'missing' | 'not_applicable'
  note: string
  evidence_ids: string[]
}

export interface ChatPlaybook {
  id: string
  title: string
  status: 'draft' | 'approved'
}

export type FeedbackTag = 'too_long' | 'wrong' | 'missing' | 'not_useful'

export interface FeedbackRequest {
  question: string
  history: { role: 'user' | 'assistant'; text: string }[]
  answer: { text: string; details?: string | null; sources: string[]; trace: string[]; version?: string | null; model?: string | null; execution_mode?: string | null; playbook?: string | null }
  thumbs: 'up' | 'down'
  tag?: FeedbackTag | null
  comment?: string | null
}

export interface ChatAnswer {
  text: string
  sources: SourceRef[]
  draft: string | null
  review_card: string | null
  review_email_id: string | null
  llm_status: 'ok' | 'failed' | 'skipped'
  llm_model?: string | null
  details?: string | null // v6: evidence and missing items, behind "Show basis"
  evidence?: ChatEvidence[] // v7: key claims with a quote, checked in code
  steps?: ChatStep[]
  playbook?: ChatPlaybook | null
  version?: string | null
  execution_mode?: string | null
  capability_authority?: string | null
  reasoning_trace?: string[]
  models?: Record<string, string>
  model_note?: string | null
}
