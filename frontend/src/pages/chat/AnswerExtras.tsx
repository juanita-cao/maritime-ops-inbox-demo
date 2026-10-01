// Under a chat answer (design_agent_e16_v7.md 7.3 and 8, v7.1 section 5): "How I answered" (the
// operation guide's steps, or the processing trace; debug view only) and the thumbs.
import { useState } from 'react'
import { Button, Input, Tag } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, DislikeOutlined, LikeOutlined, MinusCircleOutlined } from '@ant-design/icons'
import { api } from '../../api/client'
import type { FeedbackTag } from '../../api/types'
import { c } from '../../theme'
import { feedbackBody, type ChatTurnVM } from '../../vm/chat'

const STEP_ICON = {
  done: <CheckCircleFilled style={{ color: '#2e8b57' }} />,
  missing: <CloseCircleFilled style={{ color: '#c0392b' }} />,
  not_applicable: <MinusCircleOutlined style={{ color: '#8a8a8a' }} />,
}

export function HowAnswered({ turn }: { turn: ChatTurnVM }) {
  const [open, setOpen] = useState(false)
  const steps = turn.steps ?? []
  const trace = turn.trace ?? []
  if (steps.length === 0 && trace.length === 0) return null
  return (
    <div>
      <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }} onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide how I answered ▲' : 'How I answered ▼'}
      </Button>
      {open && (
        <div style={{ marginTop: 6, fontSize: 13, background: c.surface2, border: `1px solid ${c.border}`, borderRadius: 8, padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {steps.length > 0
            ? steps.map((s) => (
                <div key={s.step_id} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', color: s.status === 'missing' ? '#c0392b' : c.text }}>
                  <span style={{ marginTop: 3 }}>{STEP_ICON[s.status]}</span>
                  <span>
                    <b>{s.primitive}</b> · {s.text}
                    {s.note && <span style={{ color: c.muted }}> — {s.note}</span>}
                    {s.evidence_ids.length > 0 && <span style={{ color: c.muted }}> [{s.evidence_ids.join(', ')}]</span>}
                  </span>
                </div>
              ))
            : trace.map((t, i) => <div key={i} style={{ color: c.muted }}>{t}</div>)}
        </div>
      )}
    </div>
  )
}

const TAGS: { id: FeedbackTag; label: string }[] = [
  { id: 'too_long', label: 'Too long' },
  { id: 'wrong', label: 'Wrong' },
  { id: 'missing', label: 'Missing' },
  { id: 'not_useful', label: 'Not useful' },
]

export function FeedbackBar({ turn, question, history }: { turn: ChatTurnVM; question: string; history: { role: 'user' | 'assistant'; text: string }[] }) {
  const [state, setState] = useState<'idle' | 'down' | 'sent'>('idle')
  const [tag, setTag] = useState<FeedbackTag | null>(null)
  const [comment, setComment] = useState('')
  const send = async (thumbs: 'up' | 'down') => {
    setState('sent')
    await api.feedback(feedbackBody(turn, question, history, thumbs, thumbs === 'down' ? tag : null, thumbs === 'down' ? comment.trim() || null : null))
  }
  if (state === 'sent') return <span style={{ fontSize: 12, color: c.muted }}>Thanks, noted.</span>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
        <Button size="small" type="text" icon={<LikeOutlined />} aria-label="Helpful" onClick={() => send('up')} />
        <Button size="small" type="text" icon={<DislikeOutlined />} aria-label="Not helpful" onClick={() => setState('down')} />
      </span>
      {state === 'down' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
            {TAGS.map((t) => (
              <Tag.CheckableTag key={t.id} checked={tag === t.id} onChange={() => setTag(tag === t.id ? null : t.id)}>{t.label}</Tag.CheckableTag>
            ))}
          </span>
          <Input size="small" maxLength={500} placeholder="What was wrong? (optional)" value={comment} onChange={(e) => setComment(e.target.value)} onPressEnter={() => send('down')} />
          <span><Button size="small" type="primary" onClick={() => send('down')}>Send</Button></span>
        </div>
      )}
    </div>
  )
}
