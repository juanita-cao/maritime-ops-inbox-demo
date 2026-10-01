// App shell: ProLayout sidebar (Chat first, then Email, Overview, Vessel, Action; design_frontend.md
// section 6 and U3), the one UI state of F-State, the shared result toast with Undo, and a data
// version that every page reloads on after a change anywhere.
import { useCallback, useEffect, useReducer, useState } from 'react'
import { ProLayout } from '@ant-design/pro-components'
import { Button, ConfigProvider, Drawer, Empty, Menu } from 'antd'
import { ArrowLeftOutlined, CheckSquareOutlined, MailOutlined, MenuOutlined, MessageOutlined } from '@ant-design/icons'
import { AnchorIcon, ShipIcon } from './components/icons'
import { api } from './api/client'
import { initialState, reduce, type Screen, type UiState } from './state/reducer'
import { DEFAULT_MODE, MODES, antdTheme, applyMode, c, sideTokens, type ModeId } from './theme'
import { EmailPage } from './pages/email/EmailPage'
import { ActionPage } from './pages/action/ActionPage'
import { OverviewPage } from './pages/overview/OverviewPage'
import { VesselPage } from './pages/vessel/VesselPage'
import { Toast } from './components/Toast'
import { Mascot } from './components/Mascot'
import { ModeContext } from './components/modeContext'
import { ChatPage } from './pages/chat/ChatPage'
import type { ChatTurnVM } from './vm/chat'
import type { CorrectOptions } from './pages/email/FieldList'

const DISCLAIMER =
  'AI-generated suggestions may contain errors. Please verify against the original email and the charter party before acting.'

const MENU: { key: Screen; name: string; icon: React.ReactNode }[] = [
  { key: 'chat', name: 'Chat', icon: <MessageOutlined /> },
  { key: 'email', name: 'Email', icon: <MailOutlined /> },
  { key: 'overview', name: 'Fleet Overview', icon: <AnchorIcon /> },
  { key: 'vessel', name: 'Vessel', icon: <ShipIcon /> },
  { key: 'action', name: 'Action', icon: <CheckSquareOutlined /> },
]

const SCREENS: Screen[] = ['chat', 'email', 'overview', 'vessel', 'action']

/** Deep link: #/email/E054 opens that email; #/vessel/VSL-12 that vessel. */
function fromHash(hash: string): UiState {
  const [screen, id] = hash.replace(/^#\/?/, '').split('/')
  if (!SCREENS.includes(screen as Screen)) return initialState
  return {
    ...initialState,
    screen: screen as Screen,
    selectedEmailId: screen === 'email' && id ? decodeURIComponent(id) : null,
    selectedVesselCode: screen === 'vessel' && id ? decodeURIComponent(id) : null,
  }
}

function toHash(s: UiState): string {
  const id = s.screen === 'email' ? s.selectedEmailId : s.screen === 'vessel' ? s.selectedVesselCode : null
  return `#/${s.screen}${id ? `/${encodeURIComponent(id)}` : ''}`
}

export default function App() {
  const [state, dispatch] = useReducer(reduce, window.location.hash, fromHash)
  const [now, setNow] = useState('')
  const [options, setOptions] = useState<CorrectOptions & { actionTypes: string[] }>({ vessels: [], eventTypes: [], actionTypes: [] })
  const [counts, setCounts] = useState<Partial<Record<Screen, number>>>({})
  const [vesselMeta, setVesselMeta] = useState<{ code: string; voyages: string[]; current: string | null }[]>([])
  const [dataVersion, setDataVersion] = useState(0)
  const [chatTurns, setChatTurns] = useState<ChatTurnVM[]>([]) // kept while switching pages

  // Mobile nav [AMENDMENT 2026-09-28, live-demo report]: ProLayout's own collapse button was
  // turned off (collapsedButtonRender={false}), so under its ~768px breakpoint the sidebar
  // auto-collapsed with no way to reopen it, and its fixed rail could sit over page content.
  // Below 768px the sider is not rendered at all (menuRender=false); a small header bar and an
  // antd Drawer carry the same menu instead, independent of ProLayout's own responsive Sider.
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 767px)').matches)
  const [drawerOpen, setDrawerOpen] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)')
    const onChange = () => setIsMobile(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  useEffect(() => {
    if (!isMobile) setDrawerOpen(false)
  }, [isMobile])
  const goTo = useCallback(
    (screen: Screen) => {
      dispatch({ type: 'goTo', screen })
      setDrawerOpen(false)
    },
    [dispatch],
  )
  const [mode, setMode] = useState<ModeId>(() => {
    const asked = new URLSearchParams(window.location.search).get('mode') as ModeId | null
    if (asked && MODES.some((m) => m.id === asked)) return asked
    try {
      const saved = localStorage.getItem('mm-mode') as ModeId | null
      return saved && MODES.some((m) => m.id === saved) ? saved : DEFAULT_MODE
    } catch {
      return DEFAULT_MODE
    }
  })
  useEffect(() => {
    applyMode(mode)
    try {
      localStorage.setItem('mm-mode', mode)
    } catch {
      // storage blocked: the mode lasts for this visit only
    }
  }, [mode])

  const loadCounts = useCallback(async () => {
    const [queue, tasks] = await Promise.all([api.reviewQueue(), api.tasks()])
    setCounts({
      email: queue.kind === 'ok' ? queue.data.items.filter((i) => i.status === 'open').length : undefined,
      action: tasks.kind === 'ok' ? new Set(tasks.data.groups.flatMap((g) => g.items.map((i) => i.task_id))).size : undefined,
    })
  }, [])

  const dataChanged = useCallback(() => {
    setDataVersion((v) => v + 1)
    loadCounts()
  }, [loadCounts])

  const undo = async () => {
    const token = state.toast?.undoToken
    if (!token) return
    dispatch({ type: 'undo' })
    const r = await api.undo(token)
    if (r.kind === 'error') {
      dispatch({ type: 'undone', toast: { kind: 'error', message: 'Could not undo, nothing was changed', undoToken: null } })
      return
    }
    const res = r.data
    const message =
      res.status === 'applied'
        ? 'Undone'
        : res.reason === 'later_change_exists'
          ? 'A later change exists, so this cannot be undone'
          : res.reason === 'already_decided'
            ? 'Already undone'
            : `Not undone (${res.reason ?? res.status})`
    dispatch({ type: 'undone', toast: { kind: res.status === 'applied' ? 'undone' : 'info', message, undoToken: null } })
    dataChanged()
  }

  useEffect(() => {
    const hash = toHash(state)
    if (window.location.hash !== hash) window.history.replaceState(null, '', hash)
  }, [state])

  useEffect(() => {
    api.health().then((r) => r.kind === 'ok' && setNow(r.data.now))
    Promise.all([api.taxonomy(), api.vessels()]).then(([tax, ves]) => {
      setOptions({
        eventTypes: tax.kind === 'ok' ? tax.data.event_types ?? [] : [],
        actionTypes: tax.kind === 'ok' ? tax.data.action_type ?? [] : [],
        vessels: ves.kind === 'ok' ? ves.data.map((v) => ({ code: v.vessel_code, voyages: v.voyages })) : [],
      })
      if (ves.kind === 'ok') setVesselMeta(ves.data.map((v) => ({ code: v.vessel_code, voyages: v.voyages, current: v.current_voyage })))
    })
    loadCounts()
  }, [loadCounts])

  return (
    <ModeContext.Provider value={{ mode, setMode }}>
    <ConfigProvider theme={antdTheme(mode)}>
    <ProLayout
      title="Marine Mind"
      logo={
        <span style={{ width: 30, height: 30, borderRadius: 8, background: c.accent, color: c.surface, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
          <ShipIcon style={{ fontSize: 19 }} />
        </span>
      }
      layout="side"
      fixSiderbar
      siderWidth={232}
      collapsedButtonRender={false}
      menuRender={isMobile ? false : undefined}
      headerRender={isMobile ? false : undefined}
      location={{ pathname: `/${state.screen}` }}
      route={{ path: '/', routes: MENU.map((m) => ({ path: `/${m.key}`, name: m.name, icon: m.icon })) }}
      menuItemRender={(item, dom) => {
        const key = (item.path ?? '').slice(1) as Screen
        const count = counts[key]
        return (
          <a onClick={() => goTo(key)} style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
            {dom}
            {count ? (
              <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, padding: '0 8px', borderRadius: 999, background: c.accentBg, color: c.accent, lineHeight: '20px' }}>
                {count}
              </span>
            ) : null}
          </a>
        )
      }}
      menuFooterRender={() => (
        <div style={{ padding: 12, fontSize: 12, color: c.sideMuted }}>
          <Mascot todo={(counts.email ?? 0) + (counts.action ?? 0)} />
          Demo workspace
          <br />
          Sanitized sample data
        </div>
      )}
      token={{
        bgLayout: 'transparent',
        sider: sideTokens(mode),
        pageContainer: { paddingBlockPageContainerContent: 24, paddingInlinePageContainerContent: 32 },
      }}
    >
      <div style={{ padding: isMobile ? '0 16px 16px' : '24px 32px 16px', minHeight: '100vh', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
        {isMobile ? (
          <div
            style={{
              position: 'sticky', top: 0, zIndex: 10, display: 'flex', alignItems: 'center', gap: 10,
              margin: '0 -16px 16px', padding: '10px 16px', background: c.surface, borderBottom: `1px solid ${c.border}`,
            }}
          >
            <button
              type="button"
              aria-label="Open menu"
              onClick={() => setDrawerOpen(true)}
              style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 36, height: 36, border: `1px solid ${c.border}`, borderRadius: 8, background: c.surface2, color: c.text, fontSize: 18 }}
            >
              <MenuOutlined />
            </button>
            <span style={{ fontWeight: 600, color: c.text }}>{MENU.find((m) => m.key === state.screen)?.name ?? 'Marine Mind'}</span>
          </div>
        ) : null}
        <div style={{ flexGrow: 1 }}>
          {state.cameFromChat && state.screen !== 'chat' && (
            <Button type="link" icon={<ArrowLeftOutlined />} style={{ padding: 0, marginBottom: 8 }} onClick={() => dispatch({ type: 'goTo', screen: 'chat' })}>
              Back to chat
            </Button>
          )}
          {state.screen === 'email' ? (
            <EmailPage state={state} dispatch={dispatch} now={now} options={options} onDataChanged={dataChanged} dataVersion={dataVersion} />
          ) : state.screen === 'chat' ? (
            <ChatPage dispatch={dispatch} turns={chatTurns} setTurns={setChatTurns} now={now} actionTypes={options.actionTypes} onDataChanged={dataChanged} dataVersion={dataVersion} />
          ) : state.screen === 'action' ? (
            <ActionPage dispatch={dispatch} dataVersion={dataVersion} vessels={vesselMeta.map((v) => v.code)} />
          ) : state.screen === 'vessel' ? (
            <VesselPage state={state} dispatch={dispatch} dataVersion={dataVersion} vessels={vesselMeta} onDataChanged={dataChanged} />
          ) : state.screen === 'overview' ? (
            <OverviewPage dispatch={dispatch} dataVersion={dataVersion} />
          ) : (
            <Empty style={{ marginTop: 120 }} description={`${MENU.find((m) => m.key === state.screen)?.name} page not found.`} />
          )}
        </div>
        <div style={{ paddingTop: 20, fontSize: 12, color: c.muted, textAlign: 'center' }}>{DISCLAIMER}</div>
        <div style={{ paddingTop: 4, fontSize: 11, color: c.muted, textAlign: 'center', opacity: 0.8 }}>
          © {new Date().getFullYear()} InnerDrive Studio. All rights reserved.
        </div>
        <Toast state={state} onUndo={undo} onClose={() => dispatch({ type: 'dismissToast' })} />
      </div>
      <Drawer
        placement="left"
        open={isMobile && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={248}
        closable={false}
        styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column' } }}
      >
        <Menu
          mode="inline"
          selectedKeys={[state.screen]}
          items={MENU.map((m) => ({
            key: m.key,
            icon: m.icon,
            label: (
              <span style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                {m.name}
                {counts[m.key] ? (
                  <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 600, padding: '0 8px', borderRadius: 999, background: c.accentBg, color: c.accent, lineHeight: '20px' }}>
                    {counts[m.key]}
                  </span>
                ) : null}
              </span>
            ),
          }))}
          onClick={({ key }) => goTo(key as Screen)}
          style={{ border: 'none', flexGrow: 1 }}
        />
        <div style={{ padding: 12, fontSize: 12, color: c.muted }}>
          <Mascot todo={(counts.email ?? 0) + (counts.action ?? 0)} />
          Demo workspace
          <br />
          Sanitized sample data
        </div>
      </Drawer>
    </ProLayout>
    </ConfigProvider>
    </ModeContext.Provider>
  )
}
