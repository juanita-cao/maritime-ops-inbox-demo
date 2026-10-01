// Vessel page (F16, F18), laid out as the design canvas [AMENDMENT 2026-09-26 UI round U5]: on
// top the current voyage strip and the current status card, below the open items with Update.
// Every value shows its source email (evidence is never cut).
import { useCallback, useEffect, useState, type Dispatch } from 'react'
import { Button, Empty, Result, Select, Spin } from 'antd'
import { ArrowRightOutlined, WarningFilled } from '@ant-design/icons'
import { api } from '../../api/client'
import type { ManualTaskChange, NeedsAction, VesselRow } from '../../api/types'
import { Chip, PriorityBadge } from '../../components/Tags'
import { card } from '../../components/styles'
import type { UiEvent, UiState } from '../../state/reducer'
import { HIGHLIGHT_STYLE, STATUS_COLORS, c } from '../../theme'
import { buildVessel, buildVoyageView, type TaskVM, type VesselVM, type VoyageViewVM } from '../../vm/pages'
import { UpdateTask } from './UpdateTask'
import { ModePicker } from '../../components/ModePicker'
import { EmailPreview, EmailRef } from '../../components/EmailPreview'

type Load =
  | { kind: 'loading' }
  | { kind: 'ok'; vm: VesselVM; voyage: VoyageViewVM | null; row: VesselRow | null }
  | { kind: 'error'; message: string }
type VesselFilter = NeedsAction

// [AMENDMENT 2026-09-26 UI round U10] no High priority filter: priority 4 and 5 show as the shaded rows
const FILTERS: VesselFilter[] = ['Action Required', 'Approval Required', 'Waiting for Reply']

function ItemRow({ t, onToggle, showEmail, onToggleEmail }: { t: TaskVM; onToggle: () => void; showEmail: boolean; onToggleEmail: () => void }) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1.4fr) minmax(0, 1fr) auto', gap: 16, alignItems: 'center',
      padding: '14px 16px', borderRadius: 10, ...(t.highlighted ? HIGHLIGHT_STYLE : {}), borderTop: t.highlighted ? undefined : `1px solid ${c.border}`,
    }}>
      <div style={{ minWidth: 0 }}>
        <button type="button" onClick={onToggleEmail} aria-expanded={showEmail} title="Show the source email"
          style={{ border: 0, background: 'transparent', padding: 0, textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, fontSize: 14, color: c.accent, textDecoration: 'underline', textDecorationColor: c.border, textUnderlineOffset: 3, overflowWrap: 'anywhere' }}>
          {t.title}
        </button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {t.actionTypes.map((a) => <Chip key={a}>{a}</Chip>)}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
        <PriorityBadge priority={t.priority} />
        <span style={{ fontSize: 12, color: t.overdue ? c.red : c.muted, fontWeight: t.overdue ? 600 : 400 }}>
          {t.overdue && <WarningFilled style={{ marginRight: 4 }} />}
          {t.dueLabel ? `Due · ${t.dueLabel}` : 'No due set'}{t.overdue ? ' · overdue' : ''}
        </span>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Button onClick={onToggle}>Update</Button>
      </div>
    </div>
  )
}

export function VesselPage({ state, dispatch, dataVersion, vessels, onDataChanged }: {
  state: UiState
  dispatch: Dispatch<UiEvent>
  dataVersion: number
  vessels: { code: string }[]
  onDataChanged: () => void
}) {
  const code = state.selectedVesselCode ?? vessels[0]?.code ?? null
  const [load, setLoad] = useState<Load>({ kind: 'loading' })
  const [editing, setEditing] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [shown, setShown] = useState<Set<string>>(new Set())
  const toggleShown = (id: string) => setShown((s) => {
    const n = new Set(s)
    if (n.has(id)) n.delete(id)
    else n.add(id)
    return n
  })

  const fetchView = useCallback(async () => {
    if (!code) return
    const [r, rows] = await Promise.all([api.vessel(code), api.vessels()])
    if (r.kind === 'error') return setLoad({ kind: 'error', message: r.message })
    const row = rows.kind === 'ok' ? rows.data.find((v) => v.vessel_code === code) ?? null : null
    setLoad({ kind: 'ok', vm: buildVessel(r.data), voyage: row ? buildVoyageView(row.voyage_details ?? [], row.current_voyage, r.data) : null, row })
    dispatch({ type: 'dataLoaded' })
  }, [code, dispatch])

  useEffect(() => {
    fetchView()
  }, [fetchView, dataVersion])

  const save = async (change: ManualTaskChange) => {
    setBusy(true)
    const r = await api.changeTask(change)
    setBusy(false)
    if (r.kind === 'error') {
      dispatch({ type: 'notify', toast: { kind: 'error', message: `Could not save, nothing was changed (${r.message})`, undoToken: null } })
      return
    }
    const res = r.data
    setEditing(null)
    dispatch({
      type: 'notify',
      toast: res.status === 'applied'
        ? { kind: 'applied', message: change.close ? 'Item closed' : 'Item updated', undoToken: res.undo_token }
        : { kind: 'info', message: 'This item changed meanwhile. Showing the current version.', undoToken: null },
    })
    onDataChanged()
  }

  const filter = state.vesselStatusFilter as VesselFilter | null

  if (!code) return <Empty description="No vessel in the knowledge base" />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>{code}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Select value={code} style={{ width: 140 }} aria-label="Vessel" options={vessels.map((v) => ({ value: v.code, label: v.code }))}
          onChange={(v) => dispatch({ type: 'goTo', screen: 'vessel', vesselCode: v })} />
          <ModePicker />
        </div>
      </div>

      {load.kind === 'loading' && <Spin style={{ margin: 40 }} />}
      {load.kind === 'error' && (
        <Result status="warning" title="Data is temporarily unavailable" subTitle={load.message} extra={<Button type="primary" onClick={fetchView}>Retry</Button>} />
      )}
      {load.kind === 'ok' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: 16, alignItems: 'stretch' }}>
            <div style={{ ...card, padding: '16px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 16, fontWeight: 600 }}>{load.voyage?.heading ?? 'Current voyage'}</span>
                <Chip tone="accent">Email + master data</Chip>
              </div>
              {load.voyage ? (
                <div style={{ display: 'flex', alignItems: 'stretch', gap: 10 }}>
                  {load.voyage.strip.map((s, i) => (
                    <div key={s.label} style={{ display: 'contents' }}>
                      {i > 0 && <ArrowRightOutlined style={{ alignSelf: 'center', color: c.muted }} />}
                      <div style={{
                        flex: 1, minWidth: 0, borderRadius: 10, padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 2,
                        border: `1px solid ${s.current ? c.accent : c.border}`, background: s.current ? c.accentBg : c.surface2,
                      }}>
                        <span style={{ fontSize: 12, color: c.muted }}>{s.label}</span>
                        <span style={{ fontSize: 16, fontWeight: 600 }}>{s.title}</span>
                        {s.lines.map((l) => (
                          <span key={l.text} style={{ fontSize: 13, color: c.text }}>
                            {l.text}
                            <EmailRef id={l.sourceEmailId} />
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ color: c.muted, fontSize: 13 }}>No voyage record for this vessel.</div>
              )}
            </div>
            <div style={{ ...card, padding: '16px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span style={{ fontSize: 16, fontWeight: 600 }}>Current status</span>
                <Chip tone="accent">From email</Chip>
              </div>
              {(load.voyage?.status ?? []).map((r) => (
                <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderTop: `1px solid ${c.border}`, fontSize: 13 }}>
                  <span style={{ color: c.muted }}>{r.label}</span>
                  <span style={{ textAlign: 'right', fontWeight: 500 }}>
                    {r.value}
                    {r.was && <span style={{ color: c.muted, fontWeight: 400 }}> (was {r.was})</span>}
                    <EmailRef id={r.sourceEmailId} />
                  </span>
                </div>
              ))}
              {!load.voyage?.status.length && <div style={{ color: c.muted, fontSize: 13 }}>No facts from emails yet.</div>}
            </div>
          </div>

          <div style={{ ...card, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 16, fontWeight: 600 }}>Open items · {code}</span>
              <span style={{ fontSize: 13, color: c.muted }}>From emails you have reviewed</span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {FILTERS.map((f) => {
                const on = filter === f
                const n = load.vm.openItems.filter((t) => t.statuses.includes(f)).length
                const fg = STATUS_COLORS[f].fg
                return (
                  <button key={f} type="button" aria-pressed={on} onClick={() => dispatch({ type: 'setVesselFilter', filter: f })}
                    style={{ padding: '5px 14px', borderRadius: 999, fontSize: 13, fontFamily: 'inherit', cursor: 'pointer',
                      border: `1px solid ${on ? fg : c.border}`,
                      background: on ? STATUS_COLORS[f].bg : c.surface,
                      color: on ? fg : c.text }}>
                    {f} <b>{n}</b>
                  </button>
                )
              })}
              <button type="button" onClick={() => { dispatch({ type: 'goTo', screen: 'email', emailId: null }); dispatch({ type: 'setFilter', filter: 'FYI - No Action' }) }}
                style={{ padding: '5px 14px', borderRadius: 999, fontSize: 13, fontFamily: 'inherit', cursor: 'pointer', border: `1px solid ${c.border}`, background: c.surface, color: c.text }}>
                FYI <b>{load.row?.counts['FYI - No Action'] ?? 0}</b>
              </button>
            </div>
            {load.vm.openItems.length === 0 && (
              <div style={{ color: c.muted, fontSize: 13, padding: '8px 0' }}>No open items. Confirm emails on the Email page to create them.</div>
            )}
            {load.vm.openItems
              .filter((t) => !filter || t.statuses.includes(filter))
              .map((t) => (
                <div key={t.taskId}>
                  <ItemRow t={t} onToggle={() => setEditing(editing === t.taskId ? null : t.taskId)}
                    showEmail={shown.has(t.taskId)} onToggleEmail={() => toggleShown(t.taskId)} />
                  {shown.has(t.taskId) && (
                    <div style={{ margin: '0 16px 10px', padding: 10, borderRadius: 10, background: c.surface2, border: `1px solid ${c.border}` }}>
                      <EmailPreview emailId={t.sourceEmailId} />
                    </div>
                  )}
                  {editing === t.taskId && <UpdateTask task={t} busy={busy} onSave={save} onCancel={() => setEditing(null)} />}
                </div>
              ))}
          </div>
        </>
      )}
    </div>
  )
}
