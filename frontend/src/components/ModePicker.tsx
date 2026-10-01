// The colour mode picker (U13), placed at the right end of each page's title row (U14).
import { useContext } from 'react'
import { Select } from 'antd'
import { MODES, c } from '../theme'
import { ModeContext } from './modeContext'

export function ModePicker() {
  const { mode, setMode } = useContext(ModeContext)
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: c.muted }}>Mode</span>
      <Select value={mode} onChange={setMode} style={{ width: 150 }} aria-label="Colour mode"
        options={MODES.map((m) => ({ value: m.id, label: m.name }))} />
    </span>
  )
}
