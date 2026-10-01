// Fleet Overview page (F13): the fleet table with status counts; a number opens the vessel filtered
// to that status. [AMENDMENT 2026-09-26 UI round U4, owner] summary cards, review queue and applied
// reports removed from this page (the Email page filters and the Action page cover them).
import { useCallback, useEffect, useState, type Dispatch } from 'react'
import { Button, Result, Spin } from 'antd'
import { api } from '../../api/client'
import type { NeedsAction, VesselView } from '../../api/types'
import { Chip } from '../../components/Tags'
import { card } from '../../components/styles'
import { ModePicker } from '../../components/ModePicker'
import type { UiEvent } from '../../state/reducer'
import { STATUS_COLORS, c } from '../../theme'
import { OVERVIEW_STATUSES, buildOverview, type OverviewVM } from '../../vm/pages'

type Load = { kind: 'loading' } | { kind: 'ok'; vm: OverviewVM } | { kind: 'error'; message: string }

export function OverviewPage({ dispatch, dataVersion }: { dispatch: Dispatch<UiEvent>; dataVersion: number }) {
  const [load, setLoad] = useState<Load>({ kind: 'loading' })

  const fetchAll = useCallback(async () => {
    const [rows, queue] = await Promise.all([api.vessels(), api.reviewQueue()])
    if (rows.kind === 'error') return setLoad({ kind: 'error', message: rows.message })
    const views = await Promise.all(rows.data.map((r) => api.vessel(r.vessel_code)))
    const ok = views.flatMap((v) => (v.kind === 'ok' ? [v.data] : [])) as VesselView[]
    setLoad({ kind: 'ok', vm: buildOverview(rows.data, ok, queue.kind === 'ok' ? queue.data : null) })
    dispatch({ type: 'dataLoaded' })
  }, [dispatch])

  useEffect(() => {
    fetchAll()
  }, [fetchAll, dataVersion])

  const openVessel = (code: string, filter: NeedsAction | 'High priority' | null = null) =>
    dispatch({ type: 'goTo', screen: 'vessel', vesselCode: code, vesselFilter: filter })

  if (load.kind === 'loading') return <Spin style={{ margin: 60 }} />
  if (load.kind === 'error') {
    return <Result status="warning" title="Data is temporarily unavailable" subTitle={load.message} extra={<Button type="primary" onClick={fetchAll}>Retry</Button>} />
  }
  const vm = load.vm
  const grid = '1.1fr 0.7fr 1.8fr repeat(4, 0.8fr)'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>Fleet Overview</h1>
        <ModePicker />
      </div>

      <div style={card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
          <span style={{ fontSize: 16, fontWeight: 600 }}>Vessels</span>
          <Chip tone="accent">Email + master data</Chip>
        </div>
        <div style={{ fontSize: 13, color: c.muted, marginBottom: 4 }}>Click a number to open that vessel with the items in that status. An item with several statuses counts in each.</div>
        <div style={{ display: 'grid', gridTemplateColumns: grid, gap: 12, padding: '8px 4px', fontSize: 12, fontWeight: 500, color: c.muted }}>
          <div>Vessel</div><div>Voyage</div><div>Latest</div>
          {OVERVIEW_STATUSES.map((s) => (
            <div key={s} style={{ textAlign: 'center', fontWeight: 600, color: STATUS_COLORS[s].fg }}>{s === 'FYI - No Action' ? 'FYI' : s}</div>
          ))}
        </div>
        {vm.vessels.map((v) => (
          <div key={v.code} style={{ display: 'grid', gridTemplateColumns: grid, gap: 12, padding: '12px 4px', borderTop: `1px solid ${c.border}`, alignItems: 'center' }}>
            <div><Button type="link" style={{ padding: 0, fontWeight: 600 }} onClick={() => openVessel(v.code)}>{v.code}</Button></div>
            <div>{v.voyage ?? '—'}</div>
            <div style={{ fontSize: 13 }}>{v.latest}</div>
            {OVERVIEW_STATUSES.map((s) => {
              const n = v.counts[s] ?? 0
              return (
                <div key={s} style={{ textAlign: 'center' }}>
                  {n === 0 ? (
                    <span style={{ color: c.muted }}>–</span>
                  ) : (
                    <button type="button" onClick={() => (s === 'FYI - No Action' ? openVessel(v.code) : openVessel(v.code, s))}
                      style={{ minWidth: 34, minHeight: 30, padding: '0 10px', border: 0, borderRadius: 999, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600, background: STATUS_COLORS[s].bg, color: STATUS_COLORS[s].fg }}>
                      {n}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        ))}
        <div style={{ fontSize: 12, color: c.muted, paddingTop: 10, borderTop: `1px solid ${c.border}` }}>
          Counts include only emails you have reviewed and reports filed automatically. Priority is set per action (1–5); items at 4–5 are shaded light blue.
        </div>
      </div>
    </div>
  )
}
