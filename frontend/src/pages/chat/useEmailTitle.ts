// Email subject and date for the reference list: fetched once per id, shown as the id until it arrives.
import { useEffect, useState } from 'react'
import { api } from '../../api/client'

const cache = new Map<string, string>()

export function useEmailTitle(id: string, fallback: string): string {
  const [title, setTitle] = useState(cache.get(id) ?? null)
  useEffect(() => {
    if (title) return
    let live = true
    api.email(id).then((r) => {
      if (r.kind !== 'ok') return
      const e = r.data.email
      const t = `${e.subject || '(no subject)'}${e.sent_time ? ` · ${e.sent_time.slice(0, 10)}` : ''}`
      cache.set(id, t)
      if (live) setTitle(t)
    })
    return () => { live = false }
  }, [id, title])
  return title ?? fallback
}
