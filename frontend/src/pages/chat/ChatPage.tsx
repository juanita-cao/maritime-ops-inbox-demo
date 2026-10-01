// Chat page (F21, U3): ask in plain words; answers show their sources as chips that open the page,
// drafts come with Copy and are never sent, and a review question brings the review card.
import { useEffect, useRef, useState, type Dispatch } from 'react'
import { Button, Input, Tooltip } from 'antd'
import { CopyOutlined, MailOutlined, SendOutlined, CheckSquareOutlined, AppstoreOutlined, PlusOutlined } from '@ant-design/icons'
import { ShipIcon } from '../../components/icons'
import { api } from '../../api/client'
import { ModePicker } from '../../components/ModePicker'
import { ChatModelPicker } from '../../components/ChatModelPicker'
import { savedChatModel } from '../../components/chatModel'
import type { UiEvent } from '../../state/reducer'
import { c } from '../../theme'
import { SUGGESTIONS, buildAnswerTurn, buildReferences, citeParts, evidenceFor, demoTurns, historyOf, userTurn, type AnswerPart, type ChatTurnVM, type ReferenceVM } from '../../vm/chat'
import { ChatReviewCard } from './ChatReviewCard'
import { FeedbackBar, HowAnswered } from './AnswerExtras'
import { useEmailTitle } from './useEmailTitle'

/** `?debug=1` shows how the answer was made and which models ran; users never see it (design 7.1 section 5). */
const DEBUG = new URLSearchParams(window.location.search).get('debug') === '1'

/** The demo is loaded once per page load; "New chat" then really starts empty. */
let demoOpened = false

const ICON = { email: <MailOutlined />, vessel: <ShipIcon />, task: <CheckSquareOutlined />, page: <AppstoreOutlined /> }

/** The model may mark words as **bold**: show them bold instead of the stars. */
function withBold(text: string) {
  return text.split(/(\*\*[^*\n]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  )
}

function Basis({ turn, parts, onEmail, onVessel }: { turn: ChatTurnVM; parts: AnswerPart[]; onEmail: (id: string, quote: string | null) => void; onVessel: (code: string) => void }) {
  const [open, setOpen] = useState(false)
  const zh = /[一-鿿]/.test(turn.text)
  const guide = turn.playbook
  return (
    <div>
      <Button type="link" size="small" style={{ padding: 0, height: 'auto', fontSize: 12 }} onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide basis ▲' : 'Show basis ▼'}
      </Button>
      {open && (
        <div style={{ marginTop: 6, fontSize: 13, whiteSpace: 'pre-wrap', color: c.muted, background: c.surface2, border: `1px solid ${c.border}`, borderRadius: 8, padding: '8px 12px' }}>
          {guide && <div>{zh ? '按操作指引：' : 'Followed operation guide: '}<strong>{guide.title}</strong>{guide.status === 'draft' ? (zh ? '（草稿）' : ' (draft)') : ''}</div>}
          {turn.details && <AnswerText parts={parts} turn={turn} onEmail={onEmail} onVessel={onVessel} />}
        </div>
      )}
    </div>
  )
}

function Cite({ part, turn, onEmail }: { part: AnswerPart; turn: ChatTurnVM; onEmail: (id: string, quote: string | null) => void }) {
  const id = part.link!.id
  const title = useEmailTitle(id, id)
  const ev = evidenceFor(turn, id)
  return (
    <Tooltip title={<>{title}{ev && <div style={{ marginTop: 4, opacity: 0.85 }}>{ev.claim}: “{ev.quote}”</div>}</>}>
      <a style={{ cursor: 'pointer', color: c.accent, textDecoration: 'underline dotted' }} onClick={() => onEmail(id, ev?.quote ?? null)}>{part.text}</a>
    </Tooltip>
  )
}

/** v7.1: an email in the answer is a number [n] linking to the reference list; a vessel code is a link. */
function AnswerText({ parts, turn, onEmail, onVessel }: { parts: AnswerPart[]; turn: ChatTurnVM; onEmail: (id: string, quote: string | null) => void; onVessel: (code: string) => void }) {
  return (
    <>
      {parts.map((p, i) => {
        if (!p.link) return <span key={i}>{withBold(p.text)}</span>
        if (p.link.kind === 'email') return <Cite key={i} part={p} turn={turn} onEmail={onEmail} />
        return <a key={i} style={{ cursor: 'pointer', color: c.accent, textDecoration: 'underline dotted' }} onClick={() => onVessel(p.link!.id)}>{p.text}</a>
      })}
    </>
  )
}

function Reference({ r, onOpen }: { r: ReferenceVM; onOpen: (r: ReferenceVM) => void }) {
  const title = useEmailTitle(r.id, r.label)
  return (
    <div style={{ display: 'flex', gap: 6, fontSize: 12 }}>
      <span style={{ color: c.muted, minWidth: 22 }}>{r.n !== null ? `[${r.n}]` : ICON[r.kind]}</span>
      <a style={{ cursor: 'pointer', color: c.accent }} onClick={() => onOpen(r)}>{r.kind === 'email' ? title : r.label}</a>
    </div>
  )
}

function Draft({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 14, background: c.surface2, border: `1px solid ${c.border}`, borderRadius: 8, padding: '10px 12px' }}>{text}</pre>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button size="small" icon={<CopyOutlined />} onClick={() => navigator.clipboard?.writeText(text).then(() => setCopied(true))}>
          {copied ? 'Copied' : 'Copy'}
        </Button>
        <span style={{ fontSize: 12, color: c.muted }}>Draft only: check the charter party first. Nothing is sent from the chat.</span>
      </div>
    </div>
  )
}

export function ChatPage({ dispatch, turns, setTurns, now, actionTypes, onDataChanged, dataVersion }: {
  dispatch: Dispatch<UiEvent>
  turns: ChatTurnVM[]
  setTurns: (f: (t: ChatTurnVM[]) => ChatTurnVM[]) => void
  now: string
  actionTypes: string[]
  onDataChanged: () => void
  dataVersion: number
}) {
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [model, setModel] = useState<string | null>(DEBUG ? savedChatModel : null) // visitors always get the default (hybrid); the picker is for testing
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    dispatch({ type: 'dataLoaded' })
  }, [dispatch])
  useEffect(() => {
    // the page opens on the recorded demo conversation (once per page load, and only while the chat is empty)
    if (demoOpened || turns.length > 0) return
    demoOpened = true
    api.chatDemo().then((r) => {
      if (r.kind === 'ok' && r.data.items.length > 0) setTurns((t) => (t.length > 0 ? t : demoTurns(r.data.items)))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (turns[turns.length - 1]?.demo) return // the recorded demo opens at its first question, not at its end
    end.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [turns.length, sending]) // eslint-disable-line react-hooks/exhaustive-deps

  const send = async (question: string) => {
    const q = question.trim()
    if (!q || sending) return
    const history = historyOf(turns)
    setTurns((t) => [...t, userTurn(q)])
    setInput('')
    setSending(true)
    const r = await api.chat({ question: q, history, model })
    setSending(false)
    setTurns((t) => [
      ...t,
      r.kind === 'ok'
        ? buildAnswerTurn(r.data, dataVersion)
        : { role: 'assistant', text: 'I cannot answer that now; the pages still show everything.', sources: [], draft: null, reviewCard: null, failed: true },
    ])
  }

  const open = (r: ReferenceVM) => dispatch({ type: 'goTo', screen: r.target.screen, emailId: r.target.emailId, vesselCode: r.target.vesselCode, fromChat: true })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>Chat</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button icon={<PlusOutlined />} onClick={() => setTurns(() => [])} disabled={sending || turns.length === 0}>New chat</Button>
          {DEBUG && <ChatModelPicker value={model} onChange={setModel} />}
          <ModePicker />
        </div>
      </div>
      <div style={{ fontSize: 13, color: c.muted, marginTop: -8 }}>
        Ask about vessels, emails and tasks, and review new emails here. Every answer lists the emails it comes from. The AI suggests; nothing is saved until you confirm.
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {turns.map((t, i) => {
          const body = citeParts(t.text)
          const basis = citeParts(t.details ?? '', body.cited) // the answer and its basis share one numbering
          const parts = body.parts
          const refs = buildReferences(t, basis.cited)
          const onEmail = (id: string, quote: string | null) => dispatch({ type: 'goTo', screen: 'email', emailId: id, quote, fromChat: true })
          const onVessel = (code: string) => dispatch({ type: 'goTo', screen: 'vessel', vesselCode: code, fromChat: true })
          return t.role === 'user' ? (
            <div key={i} style={{ alignSelf: 'flex-end', maxWidth: '75%', background: c.accent, color: c.surface, borderRadius: '14px 14px 4px 14px', padding: '10px 14px', fontSize: 14 }}>
              {t.text}
            </div>
          ) : (
            <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span style={{ flexShrink: 0, width: 28, height: 28, borderRadius: 999, background: c.accentBg, color: c.accent, fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>AI</span>
              <div style={{ flexGrow: 1, minWidth: 0, background: c.surface, border: `1px solid ${c.border}`, borderRadius: '4px 14px 14px 14px', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ fontSize: 14, whiteSpace: 'pre-wrap', color: t.failed ? c.muted : c.text }}>
                  <AnswerText parts={parts} turn={t} onEmail={onEmail} onVessel={onVessel} />
                </div>
                {t.draft && <Draft text={t.draft} />}
                {(t.details || t.playbook) && <Basis turn={t} parts={basis.parts} onEmail={onEmail} onVessel={onVessel} />}
                {DEBUG && <HowAnswered turn={t} />}
                {t.reviewCard && (
                  <ChatReviewCard emailId={t.reviewCard.emailId} now={now} actionTypes={actionTypes} onChanged={onDataChanged}
                    onOpenEmail={() => dispatch({ type: 'goTo', screen: 'email', emailId: t.reviewCard!.emailId, fromChat: true })} />
                )}
                {!t.failed && t.asOf && (
                  <div style={{ fontSize: 11, color: c.muted }}>
                    As of {t.asOf}{t.dataVersion !== dataVersion && ' · Records changed since this answer. Ask again to refresh.'}
                  </div>
                )}
                {DEBUG && !t.failed && (t.modelNote || t.model) && <div style={{ fontSize: 11, color: c.muted }}>Model: {t.modelNote ?? t.model}</div>}
                {!t.failed && i > 0 && <FeedbackBar turn={t} question={turns[i - 1].text} history={historyOf(turns.slice(0, i - 1))} />}
                {refs.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3, borderTop: `1px solid ${c.border}`, paddingTop: 8 }}>
                    {refs.map((r) => <Reference key={`${r.kind}-${r.id}`} r={r} onOpen={open} />)}
                  </div>
                )}
              </div>
            </div>
          )
        })}
        {sending && <div style={{ color: c.muted, fontSize: 13, paddingLeft: 38 }}>Thinking…</div>}
        {turns.length === 0 && <div style={{ color: c.muted, fontSize: 14, padding: '24px 0' }}>Start with a question below, or pick a suggestion.</div>}
        <div ref={end} />
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <Input.TextArea value={input} onChange={(e) => setInput(e.target.value)} autoSize={{ minRows: 2, maxRows: 6 }} maxLength={1000}
          placeholder="Ask about a vessel, an email or a task…" aria-label="Message"
          onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); send(input) } }} />
        <Button type="primary" icon={<SendOutlined />} onClick={() => send(input)} loading={sending} disabled={!input.trim()} aria-label="Send" />
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {SUGGESTIONS.map((q) => (
          <Button key={q} shape="round" onClick={() => send(q)} disabled={sending}>{q}</Button>
        ))}
      </div>
    </div>
  )
}
