// The source email shown in place (Vessel page), so the officer does not leave the page to check
// the evidence [AMENDMENT 2026-09-26 UI round U8].
import { useEffect, useState } from 'react'
import { Popover, Spin } from 'antd'
import { api } from '../api/client'
import { c } from '../theme'
import { buildEmailDetail, type EmailDetailVM } from '../vm/viewModels'

export function EmailPreview({ emailId, maxHeight = 320 }: { emailId: string; maxHeight?: number }) {
  const [vm, setVm] = useState<EmailDetailVM | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    api.email(emailId).then((r) => {
      if (!live) return
      if (r.kind === 'error') return setError(r.message)
      try {
        setVm(buildEmailDetail(r.data))
      } catch {
        setError('Unexpected data from the server')
      }
    })
    return () => {
      live = false
    }
  }, [emailId])
  if (error) return <span style={{ fontSize: 12, color: c.red }}>Could not load {emailId}: {error}</span>
  if (!vm) return <Spin size="small" />
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: 12, color: c.muted, lineHeight: 1.6 }}>
        <b style={{ color: c.text }}>{vm.emailId}</b> · <b style={{ color: c.text }}>From:</b> {vm.sender} · <b style={{ color: c.text }}>Sent:</b> {vm.sentDate}
        <br />
        <b style={{ color: c.text }}>Subject:</b> {vm.subject}
      </div>
      <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight, overflowY: 'auto', background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, padding: '8px 10px' }}>
        {vm.bodySegments.map((s) => s.text).join('')}
      </div>
    </div>
  )
}

/** An email id that shows the email in a popover when clicked. */
export function EmailRef({ id }: { id: string | null }) {
  if (!id) return null
  return (
    <Popover trigger="click" placement="left" destroyOnHidden content={<div style={{ width: 460 }}><EmailPreview emailId={id} maxHeight={260} /></div>}>
      <button type="button" title="Show the source email"
        style={{ border: 0, background: 'transparent', padding: 0, marginLeft: 6, cursor: 'pointer', fontFamily: 'inherit', fontSize: 11, color: c.accent, textDecoration: 'underline dotted' }}>
        {id}
      </button>
    </Popover>
  )
}
