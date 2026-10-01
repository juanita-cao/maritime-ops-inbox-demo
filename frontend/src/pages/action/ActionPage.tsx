// Action page (F19, F20): summary cards, then the three status columns (open by default, can be
// collapsed), highest priority first (D7 order from the backend); the FYI count; the Due list.
// Display only.
import { useCallback, useEffect, useState, type Dispatch } from 'react'
import { Alert, Button, Empty, Result, Select, Spin } from 'antd'
import { DownOutlined, UpOutlined, WarningFilled } from '@ant-design/icons'
import { api } from '../../api/client'
import { PriorityBadge } from '../../components/Tags'
import { TaskCard } from '../../components/TaskCard'
import { ModePicker } from '../../components/ModePicker'
import { card } from '../../components/styles'
import type { UiEvent } from '../../state/reducer'
import { HIGHLIGHT_STYLE, STATUS_COLORS, c } from '../../theme'
import { buildActionCenter, type ActionCenterVM, type TaskVM } from '../../vm/pages'

type Load = { kind: 'loading' } | { kind: 'ok'; vm: ActionCenterVM } | { kind: 'error'; message: string }

export function ActionPage({ dispatch, dataVersion, vessels }: { dispatch: Dispatch<UiEvent>; dataVersion: number; vessels: string[] }) {
  const [vessel, setVessel] = useState<string | undefined>()
  const [load, setLoad] = useState<Load>({ kind: 'loading' })
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set()) // all columns open by default
  const toggle = (name: string) => setCollapsed((s) => {
    const n = new Set(s)
    if (n.has(name)) n.delete(name)
    else n.add(name)
    return n
  })

  const fetchAll = useCallback(async () => {
    const [tasks, dues, rows] = await Promise.all([api.tasks(vessel), api.dues(vessel), api.vessels()])
    if (tasks.kind === 'error') return setLoad({ kind: 'error', message: tasks.message })
    const fyi = rows.kind === 'ok'
      ? rows.data.filter((r) => !vessel || r.vessel_code === vessel).reduce((n, r) => n + (r.counts['FYI - No Action'] ?? 0), 0)
      : 0
    setLoad({ kind: 'ok', vm: buildActionCenter(tasks.data, dues.kind === 'ok' ? dues.data : null, fyi) })
    dispatch({ type: 'dataLoaded' })
  }, [vessel, dispatch])

  useEffect(() => {
    fetchAll()
  }, [fetchAll, dataVersion])

  const goVessel = (code: string) => dispatch({ type: 'goTo', screen: 'vessel', vesselCode: code })

  // [AMENDMENT 2026-09-26 UI round U9, U10] summary cards on top; the columns below are open by
  // default and can be collapsed; priority 4 and 5 show only as shaded cards
  const summary: { key: string; label: string; fg: string; items: TaskVM[]; vessels: number }[] = []
  if (load.kind === 'ok') {
    const entry = (key: string, label: string, fg: string, items: TaskVM[]) =>
      summary.push({ key, label, fg, items, vessels: new Set(items.map((t) => t.vesselCode)).size })
    for (const g of load.vm.groups) entry(g.name, g.name, STATUS_COLORS[g.name].fg, g.items)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>Action Center</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Select allowClear placeholder="All vessels" style={{ width: 160 }} value={vessel} onChange={setVessel}
            options={vessels.map((v) => ({ value: v, label: v }))} aria-label="Vessel filter" />
          <ModePicker />
        </div>
      </div>
      {load.kind === 'loading' && <Spin style={{ margin: 40 }} />}
      {load.kind === 'error' && (
        <Result status="warning" title="Data is temporarily unavailable" subTitle={load.message}
          extra={<Button type="primary" onClick={fetchAll}>Retry</Button>} />
      )}
      {load.kind === 'ok' && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14, alignItems: 'start' }}>
            {summary.map((s) => {
              const open = !collapsed.has(s.key)
              return (
                <div key={s.key} style={{ ...card, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: `${c.glow} ${s.fg}, ${c.shadow}`,
                  // a status-coloured fill and border in the colourful modes (tint 0% elsewhere)
                  background: `linear-gradient(165deg, color-mix(in srgb, ${s.fg} ${c.tint}, ${c.surface}) 0%, ${c.surface} 55%)`,
                  borderColor: `color-mix(in srgb, ${s.fg} calc(${c.tint} * 2.4), ${c.border})` }}>
                  <button type="button" aria-expanded={open} onClick={() => toggle(s.key)} title={open ? 'Collapse' : 'Show'}
                    style={{ border: 0, background: 'transparent', textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit', padding: '16px 18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 14, fontWeight: 500, color: c.muted }}>{s.label}</span>
                      {open ? <UpOutlined style={{ color: c.muted, fontSize: 12 }} /> : <DownOutlined style={{ color: c.muted, fontSize: 12 }} />}
                    </div>
                    <div style={{ fontSize: 34, fontWeight: 600, color: s.fg, lineHeight: 1.3 }}>{s.items.length}</div>
                    <div style={{ fontSize: 13, color: c.muted }}>Across {s.vessels} vessel{s.vessels === 1 ? '' : 's'}</div>
                  </button>
                  {open && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '0 12px 12px' }}>
                      {s.items.length === 0 && <div style={{ color: c.muted, fontSize: 13, padding: '0 6px' }}>Nothing here.</div>}
                      {s.items.map((t) => (
                        <TaskCard key={t.taskId} task={t} footer={
                          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => goVessel(t.vesselCode)}>Go to {t.vesselCode} →</Button>
                        } />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          <div style={card}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
              <span style={{ fontSize: 16, fontWeight: 600 }}>Due list</span>
              <span style={{ fontSize: 13, color: c.muted }}>Every action with a due date, soonest first</span>
            </div>
            <div style={{ fontSize: 12, color: c.muted, marginBottom: 8 }}>
              Due type and date are set per action on the Email page when you confirm, and can be changed on the Vessel page.
            </div>
            {load.vm.dues === null ? (
              <Alert type="warning" showIcon message="Dues are temporarily unavailable" action={<Button size="small" onClick={fetchAll}>Retry</Button>} />
            ) : load.vm.dues.length === 0 ? (
              <Empty description="No action with a due date" />
            ) : (
              <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 4px', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: c.muted, textAlign: 'left', fontSize: 12 }}>
                    {['Due', 'Type', 'Vessel · voyage', 'Action', 'Priority', ''].map((h) => (
                      <th key={h} style={{ fontWeight: 500, padding: '4px 10px' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {load.vm.dues.map((d) => {
                    const bg = d.highlighted ? HIGHLIGHT_STYLE.background : 'transparent'
                    const cell = { padding: '8px 10px', background: bg, borderTop: `1px solid ${d.highlighted ? c.hiBorder : c.border}` }
                    return (
                      <tr key={d.actionId}>
                        <td style={{ ...cell, whiteSpace: 'nowrap', fontWeight: 600, color: d.overdue ? c.red : c.text }}>
                          {d.overdue && <WarningFilled style={{ marginRight: 4 }} />}{d.dueDate}{d.overdue && ' · overdue'}
                        </td>
                        <td style={cell}>{d.dueLabel}</td>
                        <td style={{ ...cell, whiteSpace: 'nowrap' }}>{[d.vesselCode, d.voyageNo].filter(Boolean).join(' · ')}</td>
                        <td style={cell}>{d.action}</td>
                        <td style={cell}><PriorityBadge priority={d.priority} /></td>
                        <td style={{ ...cell, textAlign: 'right' }}>
                          <Button type="link" size="small" onClick={() => goVessel(d.vesselCode)}>Open vessel →</Button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
