// Email page (F01 to F12): inbox list with filters, the original email, extracted fields and the
// review card. Server data stays in local fetch state; the UI state and its guards are F-State.
import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch } from 'react'
import { Alert, Button, Input, Result, Spin } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { api } from '../../api/client'
import type { NeedsAction, Overrides } from '../../api/types'
import { canApprove, type ProposalCtx, type UiEvent, type UiState } from '../../state/reducer'
import { CONFLICT_TEXT, SAVE_FAILED, decide } from '../../review/decide'
import { c } from '../../theme'
import {
  DataError,
  buildEmailDetail,
  buildInboxRows,
  matchesFilter,
  type EmailDetailVM,
  type InboxRowVM,
} from '../../vm/viewModels'
import { SnapColumn } from '../../components/SnapColumn'
import { ModePicker } from '../../components/ModePicker'
import { EmailText } from './EmailText'
import { FieldList, type CorrectOptions } from './FieldList'
import { FilterChips, InboxList } from './InboxList'
import { ReviewPanel } from './ReviewPanel'

export interface EmailPageProps {
  state: UiState
  dispatch: Dispatch<UiEvent>
  now: string
  options: CorrectOptions & { actionTypes: string[] }
  onDataChanged: () => void
  dataVersion: number
}

type DetailState = { kind: 'none' } | { kind: 'loading' } | { kind: 'ok'; vm: EmailDetailVM } | { kind: 'error'; message: string }


export function EmailPage({ state, dispatch, now, options, onDataChanged, dataVersion }: EmailPageProps) {
  const [rows, setRows] = useState<InboxRowVM[]>([])
  const [detail, setDetail] = useState<DetailState>({ kind: 'none' })
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  const loadList = useCallback(async () => {
    const r = await api.emails()
    if (r.kind === 'error') return r.message
    try {
      setRows(buildInboxRows(r.data))
      return null
    } catch (e) {
      return e instanceof DataError ? 'Unexpected data from the server' : String(e)
    }
  }, [])

  const loadDetail = useCallback(async (id: string) => {
    setDetail((d) => (d.kind === 'ok' && d.vm.emailId === id ? d : { kind: 'loading' }))
    const r = await api.email(id)
    if (r.kind === 'error') return setDetail({ kind: 'error', message: r.message })
    try {
      setDetail({ kind: 'ok', vm: buildEmailDetail(r.data) })
    } catch (e) {
      setDetail({ kind: 'error', message: e instanceof DataError ? 'Unexpected data from the server' : String(e) })
    }
  }, [])

  // boot and HARD retry: LOADING to READY or ERROR
  useEffect(() => {
    if (state.phase !== 'LOADING') return
    loadList().then((err) => dispatch(err ? { type: 'loadFailed', message: err } : { type: 'dataLoaded' }))
  }, [state.phase, loadList, dispatch])

  useEffect(() => {
    if (state.selectedEmailId) loadDetail(state.selectedEmailId)
    else setDetail({ kind: 'none' })
  }, [state.selectedEmailId, loadDetail])

  // opening the page shows an email on the right straight away (visitors do not know they have to click one):
  // the newest one that needs a review under the current filter, else the newest one
  useEffect(() => {
    if (state.phase !== 'READY' || state.selectedEmailId || rows.length === 0) return
    const inFilter = rows.filter((r) => matchesFilter(r, state.filter))
    const first = inFilter.find((r) => r.reviewStatus === 'To review') ?? inFilter[0]
    if (first) dispatch({ type: 'selectEmail', id: first.emailId })
  }, [state.phase, state.selectedEmailId, state.filter, rows, dispatch])

  // any data change (a decision here, an undo in the toast, a change on another page) reloads
  const refresh = onDataChanged
  const firstVersion = useRef(dataVersion)
  useEffect(() => {
    if (dataVersion === firstVersion.current) return
    loadList()
    if (state.selectedEmailId) loadDetail(state.selectedEmailId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataVersion])

  const vm = detail.kind === 'ok' && detail.vm.emailId === state.selectedEmailId ? detail.vm : null
  const proposal = vm?.proposal ?? null
  const ctx: ProposalCtx = useMemo(
    () => ({
      open: proposal?.status === 'open',
      closeWarning: proposal?.closeWarning ?? false,
      actions: proposal?.actions ?? [],
      statuses: proposal?.statuses ?? [],
    }),
    [proposal],
  )
  const submitting = state.phase === 'SUBMITTING'

  const submit = async (kind: 'approve' | 'reject') => {
    if (!proposal) return
    const { outcome } = await decide(kind, proposal, state, ctx, dispatch, now)
    if (outcome === 'conflict') setNotice(CONFLICT_TEXT)
    if (outcome !== 'refused' && outcome !== 'failed') refresh()
  }
  const approve = () => submit('approve')
  const reject = () => submit('reject')

  const rerun = async (overrides: Overrides) => {
    if (!proposal || !ctx.open) return
    dispatch({ type: 'rerun', ctx })
    const r = await api.rerun(proposal.proposalId, overrides)
    if (r.kind === 'error') return dispatch({ type: 'requestFailed', message: SAVE_FAILED })
    dispatch({ type: 'newProposal' })
    setNotice('Re-run with your correction. The earlier proposal is kept as replaced.')
    refresh()
  }

  // --- render --------------------------------------------------------------------------------

  if (state.phase === 'LOADING') return <Spin style={{ margin: 60 }} />
  if (state.phase === 'ERROR' && state.error?.severity === 'HARD') {
    return (
      <Result status="warning" title="Could not load data" subTitle={state.error.message}
        extra={<Button type="primary" onClick={() => dispatch({ type: 'retry' })}>Retry</Button>} />
    )
  }

  const q = search.trim().toLowerCase()
  const shown = rows.filter(
    (r) =>
      matchesFilter(r, state.filter) &&
      (!q || [r.subject, r.vesselCode, r.voyageNo, r.senderRole, r.eventType].some((x) => x?.toLowerCase().includes(q))),
  )
  const notMatched = rows.filter((r) => r.reviewStatus === 'Not matched').length
  const statuses: NeedsAction[] = state.statusEdits ?? proposal?.statuses ?? []
  const actions = state.actionEdits ?? proposal?.actions ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>Email</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Input prefix={<SearchOutlined />} placeholder="Search vessel, voyage, sender" aria-label="Search emails"
            value={search} onChange={(e) => setSearch(e.target.value)} allowClear style={{ width: 260 }} />
          <ModePicker />
        </div>
      </div>
      <FilterChips rows={rows} filter={state.filter} onChange={(f) => dispatch({ type: 'setFilter', filter: f })} />
      {notMatched > 0 && state.filter !== 'Not matched' && (
        <Alert type="warning" showIcon message={`${notMatched} email${notMatched > 1 ? 's' : ''} could not be matched to a vessel and need a manual check`}
          action={<Button size="small" onClick={() => dispatch({ type: 'setFilter', filter: 'Not matched' })}>Show them</Button>} />
      )}
      {notice && <Alert type="info" showIcon closable message={notice} onClose={() => setNotice(null)} />}
      {state.phase === 'ERROR' && state.error?.severity === 'SOFT' && (
        <Alert type="error" showIcon message={state.error.message}
          action={<Button size="small" onClick={() => dispatch({ type: 'retry' })}>OK</Button>} />
      )}

      <div style={{ display: 'flex', gap: 16, alignItems: 'stretch' }}>
        {/* the list column is as tall as the email and review column (at least one screen); the
            list scrolls inside it, so both sides end together */}
        <SnapColumn minHeight="calc(100vh - 250px)">
          <InboxList rows={shown} selectedId={state.selectedEmailId} onSelect={(id) => dispatch({ type: 'selectEmail', id })} />
        </SnapColumn>
        <div style={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {detail.kind === 'none' && (
            <div style={{ color: c.muted, padding: 40, textAlign: 'center' }}>Choose an email on the left to review it.</div>
          )}
          {detail.kind === 'loading' && <Spin style={{ margin: 40 }} />}
          {detail.kind === 'error' && (
            <Alert type="error" showIcon message="Could not load this email" description={detail.message}
              action={<Button size="small" onClick={() => state.selectedEmailId && loadDetail(state.selectedEmailId)}>Retry</Button>} />
          )}
          {vm && (
            <>
              <EmailText detail={vm} highlightedField={state.highlightedField} quote={state.highlightedQuote} />
              {vm.held && <Alert type="warning" showIcon message={vm.held} description="No AI result is shown for a held email." />}
              {proposal && (
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                  <div style={{ flex: '0.8 1 250px', minWidth: 0 }}>
                    <FieldList proposal={proposal} highlightedField={state.highlightedField} explainOpenFor={state.explainOpenFor}
                      onHighlight={(k) => dispatch({ type: 'setHighlight', field: k })}
                      onExplain={(k) => dispatch({ type: 'toggleExplain', field: k })}
                      options={options} busy={submitting} onRerun={rerun} />
                  </div>
                  <div style={{ flex: '1.2 1 380px', minWidth: 0 }}>
                    <ReviewPanel
                      proposal={proposal}
                      statuses={statuses}
                      actions={actions}
                      edits={state.edits}
                      editing={state.phase === 'EDITING'}
                      submitting={submitting}
                      canApprove={canApprove(state, ctx)}
                      actionTypes={options.actionTypes}
                      onToggleStatus={(s) => dispatch({ type: 'toggleStatus', status: s, ctx })}
                      onEditAction={(i, patch) => dispatch({ type: 'editAction', index: i, patch, ctx })}
                      onRemoveAction={(i) => dispatch({ type: 'removeAction', index: i, ctx })}
                      onAddAction={(a) => dispatch({ type: 'addAction', action: a, ctx })}
                      onEditField={(name, value) => dispatch({ type: 'editField', name, value, ctx })}
                      onCancelEdit={() => dispatch({ type: 'cancelEdit' })}
                      onApprove={approve}
                      onReject={reject}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
