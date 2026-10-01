// F-VM scenarios for the Action, Vessel and Overview pages (design_frontend.md Artifact 9).
import { describe, expect, it } from 'vitest'
import type { TaskRow, VesselView } from '../api/types'
import { buildActionCenter, buildOverview, buildTask, buildVessel, buildVoyageView, dueLabel } from './pages'

const taskRow = (over: Partial<TaskRow> = {}): TaskRow => ({
  task_id: 'T1', vessel: 'VSL-02', voyage: 'V203', action: 'Get the survey quote', priority: 4, due_type: 'Others',
  deadline: '2026-08-02T00:00:00+08:00', overdue: false, statuses: ['Action Required', 'Waiting for Reply'],
  source_email_id: 'E054', task_key: 'VSL-02|V203|survey:-', version: 2,
  actions: [
    { action_id: 'A1', task_id: 'T1', action_type: 'Arrange Survey', description: 'Get the quote', priority: 4, due_type: 'Others',
      due_other: 'survey quote', due_date: '2026-08-02', set_by: 'officer', source_email_id: 'E054', needs_approval: false, awaiting_reply: true },
  ],
  ...over,
})

describe('F-VM pages', () => {
  it('f_vm_s10_others_due_label_carries_its_text', () => {
    expect(dueLabel('Others', 'survey quote')).toBe('Others: survey quote')
    expect(dueLabel('Invoice', null)).toBe('Invoice')
    expect(buildTask(taskRow()).dueLabel).toBe('Others: survey quote · 2 Aug')
  })

  it('f_render_s08_task_with_two_statuses_is_in_both_groups_with_both_tags', () => {
    const row = taskRow()
    const vm = buildActionCenter({ groups: [{ name: 'Action Required', items: [row] }, { name: 'Waiting for Reply', items: [row] }] }, null, 0)
    const inGroups = vm.groups.filter((g) => g.items.some((t) => t.taskId === 'T1'))
    expect(inGroups.map((g) => g.name)).toEqual(['Action Required', 'Waiting for Reply'])
    expect(inGroups.every((g) => g.items[0].statuses.length === 2)).toBe(true)
  })

  it('f_vm_due_list_unavailable_is_not_empty', () => {
    expect(buildActionCenter({ groups: [] }, { items: [], store_status: 'unavailable' }, 0).dues).toBeNull()
  })

  it('f_vm_s07_timeline_by_event_time_not_arrival', () => {
    const view: VesselView = {
      vessel_code: 'VSL-02',
      facts: [
        { fact_key: 'eta:newcastle', value: '4 Aug', event_time: '2026-07-30T08:00:00+08:00', source_email_id: 'E2', superseded: false },
        { fact_key: 'eta:newcastle', value: '5 Aug', event_time: '2026-07-28T08:00:00+08:00', source_email_id: 'E1', superseded: true },
      ],
      timeline: [
        { event_time: '2026-07-30T08:00:00+08:00', event_type: 'Vessel Report', email_id: 'E2', changed_fact_keys: ['eta:newcastle'] },
        { event_time: '2026-07-28T08:00:00+08:00', event_type: 'Vessel Report', email_id: 'E1', changed_fact_keys: ['eta:newcastle'] },
      ],
      open_tasks: [],
      auto_applied: [],
    }
    const vm = buildVessel(view)
    expect(vm.timeline.map((t) => t.emailId)).toEqual(['E1', 'E2'])
    expect(vm.facts).toEqual([
      { key: 'eta:newcastle', label: 'ETA Newcastle', value: '4 Aug', time: '30 Jul 08:00', sourceEmailId: 'E2', wasValue: '5 Aug' },
    ])
  })

  it('f_vm_overview_counts_an_item_in_each_status', () => {
    const vm = buildOverview(
      [
        { vessel_code: 'VSL-02', voyages: [], current_voyage: 'V203', counts: { 'Action Required': 2, 'Waiting for Reply': 1 }, high_priority: 1, voyage_details: [] },
        { vessel_code: 'VSL-01', voyages: [], current_voyage: null, counts: { 'Action Required': 1 }, high_priority: 0, voyage_details: [] },
      ],
      [],
      { items: [{ proposal_id: 'P', email_id: 'E', status: 'open' }], store_status: 'ok' },
    )
    expect(vm.statusTotals.slice(0, 3).map((s) => [s.count, s.vesselCount])).toEqual([[3, 2], [0, 0], [1, 1]])
    expect([vm.highPriorityCount, vm.highPriorityVesselCount, vm.reviewQueueCount]).toEqual([1, 1, 1])
  })
})

describe('Vessel Update (A18)', () => {
  it('f_vm_update_sends_only_changed_fields_and_done_closes', async () => {
    const { buildChange, draftOf } = await import('./taskChange')
    const task = buildTask(taskRow())
    const a = task.actionItems[0]
    expect(buildChange(task, { A1: draftOf(a) }, task.statuses, false, '')).toBeNull()
    const change = buildChange(task, { A1: { ...draftOf(a), priority: 5 } }, ['Action Required'], false, ' agreed ')
    expect(change).toEqual({
      task_id: 'T1', expected_version: 2, new_statuses: ['Action Required'], close: false,
      action_changes: [{ action_id: 'A1', priority: 5 }], reason: 'agreed',
    })
    expect(buildChange(task, {}, task.statuses, true, '')).toMatchObject({ close: true, new_statuses: null, action_changes: [] })
  })
})

describe('Vessel voyage strip (U5)', () => {
  it('f_vm_voyage_strip_from_the_voyage_records_and_the_current_facts', () => {
    const fact = (key: string, value: string, time: string, email: string, superseded = false) =>
      ({ fact_key: key, value, event_time: time, source_email_id: email, superseded })
    const view: VesselView = {
      vessel_code: 'VSL-02', timeline: [], open_tasks: [], auto_applied: [],
      facts: [
        fact('sailed:dampier', '1448LT 30 Jul 2026', '2026-07-30T06:48:00+00:00', 'E053'),
        fact('sailed:dampier_p_s', '1606lt 22 Jul 2026', '2026-07-22T08:06:00+00:00', 'E012'),
        fact('eta:unknown', '1500lt 25 Jul', '2026-07-21T07:00:00+00:00', 'E010', true),
        fact('eta:newcastle', '4 Aug 15:00 LT', '2026-07-30T07:00:00+00:00', 'E053'),
        fact('eta:newcastle', '5 Aug', '2026-07-28T07:00:00+00:00', 'E040', true),
      ],
    }
    const details = [
      { voyage_no: 'V202', status: 'in progress', route: 'Dampier -> Newcastle', start: '2026-07-25', end: '2026-08-06 (expected)', facts: '' },
      { voyage_no: 'V203', status: 'planned', route: 'Rotterdam -> Santos', start: '2026-08-12 (laycan opens)', end: '', facts: 'steel products; delivery to CPY-31' },
    ]
    const vm = buildVoyageView(details, 'V202', view)!
    expect(vm.heading).toBe('Current voyage V202 · Dampier → Newcastle')
    expect(vm.strip.map((s) => [s.label, s.title, s.current])).toEqual([
      ['Done', 'Dampier', false], ['On passage', 'Newcastle', true], ['Next voyage V203', 'Rotterdam', false],
    ])
    expect(vm.strip[1].lines[0]).toEqual({ text: 'ETA 4 Aug 15:00 LT', sourceEmailId: 'E053' })
    expect(vm.status.find((r) => r.label === 'ETA Newcastle')).toMatchObject({ value: '4 Aug 15:00 LT', was: '5 Aug' })
    expect(vm.status[0].value).toBe('At sea, to Newcastle')
    expect(vm.strip[0].lines).toEqual([{ text: 'Sailed 1448LT 30 Jul 2026', sourceEmailId: 'E053' }])
  })
})
