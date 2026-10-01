// The chat model picker (v5.1 model picker), next to the colour Mode picker on the Chat page.
// Options come from GET /api/chat/models (a server allow-list); the choice is kept per browser.
import { useEffect, useState } from 'react'
import { Select } from 'antd'
import { api } from '../api/client'
import type { ChatModel } from '../api/types'
import { c } from '../theme'
import { CHAT_MODEL_KEY as KEY } from './chatModel'

export function ChatModelPicker({ value, onChange }: { value: string | null; onChange: (m: string) => void }) {
  const [models, setModels] = useState<ChatModel[]>([])

  useEffect(() => {
    api.chatModels().then((r) => {
      if (r.kind !== 'ok') return
      setModels(r.data.models)
      if (!value || !r.data.models.some((m) => m.id === value)) onChange(r.data.default)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const change = (m: string) => {
    try {
      localStorage.setItem(KEY, m)
    } catch {
      /* storage blocked: the choice still holds for this page */
    }
    onChange(m)
  }

  if (models.length === 0) return null
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: c.muted }}>Model</span>
      <Select value={value ?? undefined} onChange={change} style={{ width: 230 }} aria-label="Chat model"
        popupMatchSelectWidth={false}
        options={models.map((m) => ({
          value: m.id,
          label: m.label,
          title: m.note,
        }))}
        optionRender={(o) => {
          const m = models.find((x) => x.id === o.value)
          return (
            <div>
              <div>{m?.label}</div>
              <div style={{ fontSize: 12, color: c.muted }}>{m?.note}</div>
            </div>
          )
        }} />
    </span>
  )
}
