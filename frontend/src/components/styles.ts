// Shared inline styles of cards and section labels (canvas light theme).
import type { CSSProperties } from 'react'
import { c } from '../theme'

export const sectionLabel: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: '.06em',
  color: c.muted,
  textTransform: 'uppercase',
}

export const card: CSSProperties = {
  background: c.surface,
  border: `1px solid ${c.border}`,
  borderRadius: 12,
  padding: '14px 16px',
  boxShadow: c.shadow,
  backdropFilter: c.blur,
}
