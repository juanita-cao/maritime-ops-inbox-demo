// F-VM for the Action, Vessel and Overview pages (design_frontend.md Artifact 6): TaskVM, DueRowVM,
// ActionCenterVM, VesselVM, OverviewVM. Pure mappings; the shading rule is isHighlighted.
import type {
  DueList,
  DueType,
  NeedsAction,
  RankedTaskList,
  ReviewQueue,
  TaskAction,
  TaskRow,
  VesselRow,
  VesselView,
  VoyageDetail,
} from '../api/types'
import { factLabel, formatDate, formatTime, isHighlighted } from './viewModels'

/** "Invoice", or "Others: survey quote" (F-VM-S10). */
export function dueLabel(type: DueType | null | undefined, other: string | null | undefined): string {
  if (!type) return ''
  return type === 'Others' && other ? `Others: ${other}` : type
}

export interface TaskVM {
  taskId: string
  title: string
  vesselCode: string
  voyageNo: string | null
  statuses: NeedsAction[]
  priority: number
  highlighted: boolean
  dueLabel: string | null
  deadline: string | null
  overdue: boolean
  version: number
  sourceEmailId: string
  actionTypes: string[]
  actionItems: TaskAction[]
}

export function buildTask(t: TaskRow): TaskVM {
  const actions = t.actions ?? []
  const first = [...actions].filter((a) => a.due_date).sort((a, b) => (a.due_date! < b.due_date! ? -1 : 1))[0]
  return {
    taskId: t.task_id,
    title: t.action,
    vesselCode: t.vessel,
    voyageNo: t.voyage ?? null,
    statuses: t.statuses ?? [],
    priority: t.priority,
    highlighted: isHighlighted(t.priority),
    dueLabel: first ? `${dueLabel(first.due_type, first.due_other)} · ${formatDate(first.due_date)}` : t.deadline ? formatDate(t.deadline) : null,
    deadline: t.deadline ?? null,
    overdue: Boolean(t.overdue),
    version: t.version ?? 1,
    sourceEmailId: t.source_email_id,
    actionTypes: [...new Set(actions.map((a) => a.action_type))],
    actionItems: actions,
  }
}

export interface DueRowVM {
  taskId: string
  actionId: string
  dueDate: string
  dueLabel: string
  vesselCode: string
  voyageNo: string | null
  action: string
  priority: number
  overdue: boolean
  highlighted: boolean
}

export function buildDues(d: DueList): DueRowVM[] {
  return d.items.map((r) => ({
    taskId: r.task_id,
    actionId: r.action_id,
    dueDate: formatDate(r.due_date),
    dueLabel: dueLabel(r.due_type, r.due_other),
    vesselCode: r.vessel,
    voyageNo: r.voyage ?? null,
    action: r.action,
    priority: r.priority,
    overdue: Boolean(r.overdue),
    highlighted: isHighlighted(r.priority),
  }))
}

export interface ActionCenterVM {
  groups: { name: NeedsAction; items: TaskVM[] }[]
  dues: DueRowVM[] | null // null: the Due list is unavailable (not shown as empty)
  fyiCount: number
}

export function buildActionCenter(tasks: RankedTaskList, dues: DueList | null, fyiCount: number): ActionCenterVM {
  const names: NeedsAction[] = ['Action Required', 'Approval Required', 'Waiting for Reply']
  return {
    groups: names.map((name) => ({
      name,
      items: (tasks.groups.find((g) => g.name === name)?.items ?? []).map(buildTask),
    })),
    dues: dues && dues.store_status === 'ok' ? buildDues(dues) : null,
    fyiCount,
  }
}

// --- vessel -----------------------------------------------------------------------------

export interface FactVM {
  key: string
  label: string
  value: string
  time: string
  sourceEmailId: string
  wasValue: string | null
}

export interface TimelineVM {
  time: string
  sortKey: string
  label: string
  emailId: string
  changed: string[]
}

export interface VesselVM {
  code: string
  facts: FactVM[]
  timeline: TimelineVM[]
  openItems: TaskVM[]
  autoApplied: { emailId: string; factLabels: string[]; time: string }[]
}

export function buildVessel(v: VesselView): VesselVM {
  const facts = v.facts ?? []
  const current = facts.filter((f) => !f.superseded)
  return {
    code: v.vessel_code,
    facts: current
      .map((f) => {
        const older = facts
          .filter((x) => x.fact_key === f.fact_key && x.superseded)
          .sort((a, b) => (a.event_time < b.event_time ? 1 : -1))[0]
        return {
          key: f.fact_key,
          label: factLabel(f.fact_key),
          value: f.value,
          time: formatTime(f.event_time),
          sourceEmailId: f.source_email_id,
          wasValue: older?.value ?? null,
        }
      })
      .sort((a, b) => a.label.localeCompare(b.label)),
    // F-VM-S07: by event time, not arrival
    timeline: [...(v.timeline ?? [])]
      .sort((a, b) => (a.event_time < b.event_time ? -1 : a.event_time > b.event_time ? 1 : a.email_id.localeCompare(b.email_id)))
      .map((t) => ({
        time: formatTime(t.event_time),
        sortKey: t.event_time,
        label: t.event_type,
        emailId: t.email_id,
        changed: t.changed_fact_keys.map(factLabel),
      })),
    openItems: (v.open_tasks ?? []).map(buildTask),
    autoApplied: (v.auto_applied ?? []).map((a) => ({
      emailId: a.email_id,
      factLabels: a.fact_keys.map(factLabel),
      time: formatTime(a.applied_at),
    })),
  }
}

// --- overview ---------------------------------------------------------------------------

export interface FleetRowVM {
  code: string
  voyage: string | null
  latest: string // latest ETA or the newest fact, for the table
  counts: Record<string, number>
  highPriority: number
}

export interface OverviewVM {
  highPriorityCount: number
  highPriorityVesselCount: number
  statusTotals: { status: NeedsAction; count: number; vesselCount: number }[]
  vessels: FleetRowVM[]
  reviewQueueCount: number
  appliedReports: { emailId: string; vesselCode: string; factLabels: string[]; time: string }[]
}

export const OVERVIEW_STATUSES: NeedsAction[] = ['Action Required', 'Approval Required', 'Waiting for Reply', 'FYI - No Action']

export function buildOverview(rows: VesselRow[], views: VesselView[], queue: ReviewQueue | null): OverviewVM {
  const view = (code: string) => views.find((v) => v.vessel_code === code)
  return {
    highPriorityCount: rows.reduce((n, r) => n + r.high_priority, 0),
    highPriorityVesselCount: rows.filter((r) => r.high_priority > 0).length,
    statusTotals: OVERVIEW_STATUSES.map((status) => ({
      status,
      count: rows.reduce((n, r) => n + (r.counts[status] ?? 0), 0),
      vesselCount: rows.filter((r) => (r.counts[status] ?? 0) > 0).length,
    })),
    vessels: rows.map((r) => {
      const facts = (view(r.vessel_code)?.facts ?? []).filter((f) => !f.superseded)
      const eta = facts.filter((f) => f.fact_key.startsWith('eta:')).sort((a, b) => (a.event_time < b.event_time ? 1 : -1))[0]
      const newest = [...facts].sort((a, b) => (a.event_time < b.event_time ? 1 : -1))[0]
      const shown = eta ?? newest
      return {
        code: r.vessel_code,
        voyage: r.current_voyage,
        latest: shown ? `${factLabel(shown.fact_key)}: ${shown.value}` : '—',
        counts: r.counts,
        highPriority: r.high_priority,
      }
    }),
    reviewQueueCount: queue ? queue.items.filter((i) => i.status === 'open').length : 0,
    appliedReports: views
      .flatMap((v) =>
        v.auto_applied.map((a) => ({
          emailId: a.email_id,
          vesselCode: v.vessel_code,
          factLabels: a.fact_keys.map(factLabel),
          time: formatTime(a.applied_at),
          sortKey: a.applied_at,
        })),
      )
      .sort((a, b) => (a.sortKey < b.sortKey ? 1 : -1))
      .map((a) => ({ emailId: a.emailId, vesselCode: a.vesselCode, factLabels: a.factLabels, time: a.time })),
  }
}

// --- Vessel page: voyage strip and status card [AMENDMENT 2026-09-26 UI round U5] ------------


type RawFact = VesselView['facts'][number]

export interface StripLine {
  text: string
  sourceEmailId: string | null
}

export interface StripCardVM {
  label: string
  title: string
  lines: StripLine[]
  current: boolean
}

export interface StatusRowVM {
  label: string
  value: string
  was: string | null
  sourceEmailId: string | null
}

export interface VoyageViewVM {
  heading: string
  strip: StripCardVM[]
  status: StatusRowVM[]
}

const slug = (port: string) => port.trim().toLowerCase().split(/[\s(]/)[0]

function ports(route: string): [string, string | null] {
  const [from, to] = route.split('->').map((x) => x.trim())
  return [from || route, to || null]
}

/** The newest current fact of a kind, preferring one about the given port. */
function newest(facts: RawFact[], kind: string, port?: string | null): RawFact | null {
  const all = facts.filter((f) => !f.superseded && f.fact_key.split(':')[0] === kind)
  const here = port ? all.filter((f) => f.fact_key.includes(slug(port))) : []
  const pool = here.length ? here : all
  return pool.sort((a, b) => (a.event_time < b.event_time ? 1 : -1))[0] ?? null
}

function wasOf(facts: RawFact[], f: RawFact | null): string | null {
  if (!f) return null
  const older = facts.filter((x) => x.fact_key === f.fact_key && x.superseded).sort((a, b) => (a.event_time < b.event_time ? 1 : -1))[0]
  return older?.value ?? null
}

const line = (text: string, f: RawFact | null = null): StripLine => ({ text, sourceEmailId: f?.source_email_id ?? null })

export function buildVoyageView(details: VoyageDetail[], currentNo: string | null, view: VesselView): VoyageViewVM | null {
  const index = details.findIndex((d) => d.voyage_no === currentNo)
  const cur = details[index]
  if (!cur) return null
  const next = details[index + 1] ?? null
  // only facts of this voyage: from its start date on (a fact of the last voyage whose port was
  // read wrongly must not show as this voyage's departure)
  const start = /^\d{4}-\d{2}-\d{2}/.exec(cur.start)?.[0]
  const facts = (view.facts ?? []).filter((f) => !start || f.event_time.slice(0, 10) >= start)
  const [from, to] = ports(cur.route)
  const sailed = newest(facts, 'sailed', from)
  const completed = newest(facts, 'completed', from)
  const eta = newest(facts, 'eta', to)
  const strip: StripCardVM[] = [
    {
      label: sailed ? 'Done' : 'In port',
      title: from,
      lines: [
        ...(completed ? [line(`Completed ${completed.value}`, completed)] : []),
        ...(sailed ? [line(`Sailed ${sailed.value}`, sailed)] : []),
      ],
      current: !sailed,
    },
  ]
  if (to) {
    strip.push({
      label: sailed ? 'On passage' : 'Next port',
      title: to,
      lines: [...(eta ? [line(`ETA ${eta.value}`, eta)] : []), ...(cur.end ? [line(`Voyage ends ${cur.end}`)] : [])],
      current: Boolean(sailed),
    })
  }
  if (next) {
    strip.push({
      label: `Next voyage ${next.voyage_no}`,
      title: ports(next.route)[0],
      lines: [...(next.start ? [line(`Starts ${next.start}`)] : []), ...(next.facts ? [line(next.facts.split(';')[0])] : [])],
      current: false,
    })
  }
  const loaded = newest(facts, 'cargo_loaded_mt')
  const vlsfo = facts.find((f) => !f.superseded && f.fact_key === 'bunker_rob:vlsfo') ?? null
  const lsmgo = facts.find((f) => !f.superseded && f.fact_key === 'bunker_rob:lsmgo') ?? null
  const latest = [...facts].filter((f) => !f.superseded).sort((a, b) => (a.event_time < b.event_time ? 1 : -1))[0] ?? null
  const status: StatusRowVM[] = [
    { label: 'Status', value: sailed && to ? `At sea, to ${to}` : `In port, ${from}`, was: null, sourceEmailId: (sailed ?? null)?.source_email_id ?? null },
    ...(loaded ? [{ label: 'Loaded', value: loaded.value, was: wasOf(facts, loaded), sourceEmailId: loaded.source_email_id }] : []),
    ...(eta && to ? [{ label: `ETA ${to}`, value: eta.value, was: wasOf(facts, eta), sourceEmailId: eta.source_email_id }] : []),
    ...(vlsfo || lsmgo
      ? [{ label: 'Bunker ROB', value: [vlsfo && `VLSFO ${vlsfo.value}`, lsmgo && `LSMGO ${lsmgo.value}`].filter(Boolean).join(' · '), was: null, sourceEmailId: (vlsfo ?? lsmgo)!.source_email_id }]
      : []),
    ...(latest ? [{ label: 'Updated', value: formatTime(latest.event_time), was: null, sourceEmailId: latest.source_email_id }] : []),
  ]
  return { heading: `Current voyage ${cur.voyage_no} · ${to ? `${from} → ${to}` : from}`, strip, status }
}
