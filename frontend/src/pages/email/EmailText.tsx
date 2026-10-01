// EmailText (Artifact 7): the original email; only the segment of the highlighted field is marked.
import { useState } from 'react'
import { Alert, Button } from 'antd'
import { card, sectionLabel } from '../../components/styles'
import { c } from '../../theme'
import type { EmailDetailVM } from '../../vm/viewModels'
import { findQuote } from './findQuote'

function marked(text: string, quote: string | null) {
  const at = findQuote(text, quote)
  if (!at) return text
  return (
    <>
      {text.slice(0, at[0])}
      <mark ref={(el) => el?.scrollIntoView?.({ block: 'center' })} style={{ background: c.amberBg, color: c.text, padding: '0 2px', borderRadius: 3, outline: `1px solid ${c.amber}` }}>
        {text.slice(at[0], at[1])}
      </mark>
      {text.slice(at[1])}
    </>
  )
}

export function EmailText({ detail, highlightedField, quote = null }: { detail: EmailDetailVM; highlightedField: string | null; quote?: string | null }) {
  const body = detail.bodySegments.map((s) => s.text).join('')
  const inQuoted = !findQuote(body, quote) && findQuote(detail.quotedText, quote) !== null
  const [showQuoted, setShowQuoted] = useState(inQuoted)
  return (
    <div style={{ ...card, padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={sectionLabel}>Original email</span>
        <span style={{ fontSize: 12, fontWeight: 600, color: c.accent }}>{detail.proposalStatusLabel}</span>
      </div>
      <div style={{ fontSize: 13, color: c.muted, lineHeight: 1.6 }}>
        <b style={{ color: c.text }}>From:</b> {detail.sender} &nbsp; <b style={{ color: c.text }}>Sent:</b> {detail.sentDate}
        {detail.receivers && (
          <>
            <br />
            <b style={{ color: c.text }}>To:</b> {detail.receivers}
          </>
        )}
        <br />
        <b style={{ color: c.text }}>Subject:</b> {detail.subject}
        {detail.attachments.length > 0 && (
          <>
            <br />
            <b style={{ color: c.text }}>Attachments:</b> {detail.attachments.join(', ')}
          </>
        )}
      </div>
      {detail.proposal?.attachmentDependent && (
        <Alert type="warning" showIcon message="Content is in an attachment that was not read. Please open the original." />
      )}
      <div style={{ borderTop: `1px solid ${c.border}`, paddingTop: 10, fontSize: 14, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 420, overflowY: 'auto' }}>
        {quote && findQuote(body, quote) ? marked(body, quote) : detail.bodySegments.map((s, i) =>
          s.highlightKey && s.highlightKey === highlightedField ? (
            <mark key={i} style={{ background: c.amberBg, color: c.text, padding: '0 2px', borderRadius: 3, outline: `1px solid ${c.amber}` }}>
              {s.text}
            </mark>
          ) : (
            <span key={i}>{s.text}</span>
          ),
        )}
      </div>
      {detail.quotedText.trim() && (
        <div>
          <Button type="link" size="small" style={{ padding: 0 }} onClick={() => setShowQuoted((v) => !v)}>
            {showQuoted ? 'Hide earlier messages' : 'Show earlier messages in the thread'}
          </Button>
          {showQuoted && (
            <div style={{ marginTop: 6, fontSize: 13, color: c.muted, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 320, overflowY: 'auto', background: c.surface2, borderRadius: 8, padding: 10 }}>
              {marked(detail.quotedText, quote)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
