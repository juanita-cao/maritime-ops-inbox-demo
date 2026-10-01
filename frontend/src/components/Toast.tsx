// Toast (Artifact 7): the result message with Undo, shared by every page.
import { Button } from 'antd'
import { CheckCircleFilled, CloseOutlined, InfoCircleFilled } from '@ant-design/icons'
import type { UiState } from '../state/reducer'
import { c } from '../theme'

export function Toast({ state, onUndo, onClose }: { state: UiState; onUndo: () => void; onClose: () => void }) {
  const t = state.toast
  if (!t) return null
  const tone = t.kind === 'error' ? c.red : t.kind === 'info' ? c.amber : c.green
  return (
    <div role="status" style={{
      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)', zIndex: 1000, display: 'flex',
      alignItems: 'center', gap: 12, background: c.text, color: c.surface, borderRadius: 10, padding: '10px 14px',
      boxShadow: '0 6px 24px rgba(0,0,0,.25)', maxWidth: 'calc(100vw - 32px)',
    }}>
      {t.kind === 'applied' || t.kind === 'undone' ? <CheckCircleFilled style={{ color: c.greenBg }} /> : <InfoCircleFilled style={{ color: tone === c.red ? c.redBg : c.amberBg }} />}
      <span>{t.message}</span>
      {t.undoToken && (
        <Button size="small" onClick={onUndo} loading={state.phase === 'SUBMITTING'}>Undo</Button>
      )}
      <Button size="small" type="text" style={{ color: c.surface }} icon={<CloseOutlined />} onClick={onClose} aria-label="Close message" />
    </div>
  )
}
