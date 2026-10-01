// F-Api f_api_call (design_frontend.md Artifact 4): every backend call goes through here and
// returns a typed result; no exception escapes (F-Api-S02). A conflict is a result, not an
// error (F-Api-S01).
import type {
  ApplyResult,
  ChatAnswer,
  ChatModels,
  ChatRequest,
  FeedbackRequest,
  Decision,
  DecisionResponse,
  DueList,
  EmailDetail,
  Health,
  InboxRow,
  ManualTaskChange,
  Overrides,
  PipelineResult,
  RankedTaskList,
  ReviewQueue,
  Taxonomy,
  VesselRow,
  VesselView,
} from './types'

export type ApiResult<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'error'; status: number | null; message: string }

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

export async function apiCall<T>(
  path: string,
  init: RequestInit = {},
  fetchFn: FetchLike = fetch,
): Promise<ApiResult<T>> {
  try {
    const response = await fetchFn(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    })
    if (!response.ok) {
      let message = `HTTP ${response.status}`
      try {
        const body = await response.json()
        if (typeof body?.detail === 'string') message = body.detail
      } catch {
        // body is not JSON; keep the status text
      }
      return { kind: 'error', status: response.status, message }
    }
    return { kind: 'ok', data: (await response.json()) as T }
  } catch (e) {
    return { kind: 'error', status: null, message: e instanceof Error ? e.message : String(e) }
  }
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  health: () => apiCall<Health>('/api/health'),
  taxonomy: () => apiCall<Taxonomy>('/api/taxonomy'),
  emails: () => apiCall<InboxRow[]>('/api/emails'),
  email: (id: string) => apiCall<EmailDetail>(`/api/emails/${encodeURIComponent(id)}`),
  reviewQueue: () => apiCall<ReviewQueue>('/api/review-queue'),
  vessels: () => apiCall<VesselRow[]>('/api/vessels'),
  tasks: (vessel?: string) => apiCall<RankedTaskList>(`/api/tasks${vessel ? `?vessel=${encodeURIComponent(vessel)}` : ''}`),
  vessel: (code: string) => apiCall<VesselView>(`/api/vessels/${encodeURIComponent(code)}`),
  dues: (vessel?: string) => apiCall<DueList>(`/api/dues${vessel ? `?vessel=${encodeURIComponent(vessel)}` : ''}`),
  changeTask: (change: ManualTaskChange) =>
    apiCall<ApplyResult>(`/api/tasks/${change.task_id}/change`, post(change)),
  decide: (proposalId: string, decision: Decision) =>
    apiCall<DecisionResponse>(`/api/proposals/${proposalId}/decision`, post(decision)),
  rerun: (proposalId: string, overrides: Overrides) =>
    apiCall<PipelineResult>(`/api/proposals/${proposalId}/rerun`, post(overrides)),
  undo: (token: string) => apiCall<ApplyResult>(`/api/undo/${token}`, post()),
  // E16 v7 (docs/design_agent_e16_v7.md); '/api/chat', '/api/chat/v5.1' and '/api/chat/v6' stay frozen.
  chat: (request: ChatRequest) => apiCall<ChatAnswer>('/api/chat/v7', post(request)),
  chatDemo: () => apiCall<{ items: { question: string; answer: ChatAnswer; recorded_at?: string }[] }>('/api/chat/demo'),
  chatModels: () => apiCall<ChatModels>('/api/chat/models'),
  feedback: (request: FeedbackRequest) => apiCall<{ ok: boolean }>('/api/chat/feedback', post(request)),
  replayNext: () => apiCall<PipelineResult>('/api/demo/replay/next', post()),
  postEmail: (emailId: string, text: string) =>
    apiCall<PipelineResult>('/api/emails', post({ email_id: emailId, text })),
}
