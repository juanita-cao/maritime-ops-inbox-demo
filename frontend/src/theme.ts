// Colour modes (design_frontend.md section 6, item 1; [AMENDMENT 2026-09-26 UI round U13, owner]
// a mode picker). Pages read colours only from `c` and the pairs below. Each value is a CSS
// variable, so switching the mode swaps one palette on the page root and every page follows;
// antd gets a theme built from the same palette.
import { theme as antdAlgorithms, type ThemeConfig } from 'antd'
import type { NeedsAction } from './api/types'

export type ModeId = 'light' | 'maritime' | 'sakura' | 'neon' | 'bluewater'

// [AMENDMENT 2026-09-28 UI round U18, owner] Blue Water was the default mode
// [AMENDMENT 2026-10-01, owner] the default is Maritime Pro (a visitor who has chosen a mode keeps it: localStorage 'mm-mode')
export const DEFAULT_MODE: ModeId = 'maritime'

interface Palette {
  accent: string; accentBg: string; bg: string; surface: string; surface2: string; border: string
  text: string; muted: string; red: string; redBg: string; green: string; greenBg: string; amber: string; amberBg: string
  hi: string; hiBorder: string; hiText: string
  shadow: string; pageBg: string; blur: string
  glow: string // size of the coloured glow around status columns; '0 0 0 0' for none
  tint: string // how much of the status colour fills a status column ('0%' for none)
  side: string; sideText: string; sideMuted: string; sideActive: string; sideActiveText: string; sideBorder: string
  sideHoverText: string; sideHoverBg: string
  antdSurface: string // antd needs a solid colour to derive its shades
  arFg: string; arBg: string; apFg: string; apBg: string; wrFg: string; wrBg: string; fyiFg: string; fyiBg: string
  dark: boolean
}

const LIGHT: Palette = {
  accent: '#0B6E8F', accentBg: '#E1F1F6', bg: '#F1F4F8', surface: '#FFFFFF', surface2: '#F6F8FB', border: '#D9E0E9',
  text: '#14202B', muted: '#556575', red: '#B42318', redBg: '#FDE7E5', green: '#146C43', greenBg: '#DCF2E6',
  amber: '#93460A', amberBg: '#FCEFCF', hi: '#E8F1FC', hiBorder: '#B9D3F3', hiText: '#0B3F7A',
  shadow: '0 0 0 0 transparent', pageBg: '#F1F4F8', blur: 'none', glow: '0 0 0 0', tint: '0%',
  side: '#FFFFFF', sideText: '#14202B', sideMuted: '#556575', sideActive: '#E1F1F6', sideActiveText: '#0B6E8F', sideBorder: '#D9E0E9',
  sideHoverText: '#0B6E8F', sideHoverBg: '#F6F8FB', antdSurface: '#FFFFFF',
  arFg: '#93460A', arBg: '#FCEFCF', apFg: '#5B2FCF', apBg: '#EEE9FD', wrFg: '#1A56B8', wrBg: '#E0ECFB', fyiFg: '#485765', fyiBg: '#E9EDF1',
  dark: false,
}

// SaaS blue and white: white cards with a soft shadow, a deep navy sidebar, a bright blue accent
const MARITIME: Palette = {
  accent: '#1D4ED8', accentBg: '#E6EEFE', bg: '#F4F7FC', surface: '#FFFFFF', surface2: '#F3F6FB', border: '#DDE5F0',
  text: '#0B1F3A', muted: '#5B6B82', red: '#B91C1C', redBg: '#FDECEC', green: '#15803D', greenBg: '#E3F6EA',
  amber: '#9A4A07', amberBg: '#FEF1DC', hi: '#EAF1FF', hiBorder: '#BFD3FB', hiText: '#1E3A8A',
  shadow: '0 1px 2px rgba(11,31,58,.06), 0 4px 14px rgba(11,31,58,.06)', pageBg: 'linear-gradient(180deg, #EEF3FB 0%, #F7F9FC 320px)', blur: 'none', glow: '0 0 0 0', tint: '0%',
  side: '#0B2545', sideText: '#C8D6EA', sideMuted: '#8FA5C4', sideActive: '#1D4ED8', sideActiveText: '#FFFFFF', sideBorder: '#16335C',
  sideHoverText: '#FFFFFF', sideHoverBg: 'rgba(255,255,255,.08)', antdSurface: '#FFFFFF',
  arFg: '#9A4A07', arBg: '#FEF1DC', apFg: '#5B21B6', apBg: '#EFE9FE', wrFg: '#1D4ED8', wrBg: '#E6EEFE', fyiFg: '#475569', fyiBg: '#EDF1F6',
  dark: false,
}

// Sakura: a soft pink gradient, white frosted-glass cards, a rose accent, dark plum text for reading
const SAKURA: Palette = {
  accent: '#D6336C', accentBg: '#FCE4EC', bg: '#FBE3EB', surface: 'rgba(255,255,255,.66)', surface2: 'rgba(255,255,255,.5)',
  border: 'rgba(214,51,108,.18)', text: '#3B1F2B', muted: '#8A5A6E', red: '#B4233B', redBg: '#FDE2E6',
  green: '#1F7A4D', greenBg: '#E2F4EA', amber: '#A0460F', amberBg: '#FFEBD9', hi: '#FFE0EA', hiBorder: '#F5A3BD', hiText: '#9C1F4A',
  shadow: '0 8px 30px rgba(214,51,108,.10)', pageBg: 'linear-gradient(135deg, #FDE8EF 0%, #F9CCDA 48%, #F7DCEB 100%) fixed', blur: 'blur(14px)', glow: '0 0 0 0', tint: '0%',
  side: 'rgba(255,255,255,.34)', sideText: '#5A2A3C', sideMuted: '#9A6A7E', sideActive: 'rgba(255,255,255,.72)', sideActiveText: '#D6336C',
  sideBorder: 'rgba(214,51,108,.18)', sideHoverText: '#D6336C', sideHoverBg: 'rgba(255,255,255,.45)', antdSurface: '#FFF6F9',
  arFg: '#A0460F', arBg: '#FFEBD9', apFg: '#7B2FBF', apBg: '#F3E6FF', wrFg: '#2B5BB8', wrBg: '#E3ECFF', fyiFg: '#7A5A67', fyiBg: '#F6E4EA',
  dark: false,
}

// Neon Glow: near-black with neon halos, dark glass cards, bright status colours, coloured glows
const NEON: Palette = {
  accent: '#F472B6', accentBg: 'rgba(244,114,182,.16)', bg: '#08070D', surface: 'rgba(255,255,255,.05)', surface2: 'rgba(255,255,255,.08)',
  border: 'rgba(255,255,255,.13)', text: '#F4F1FB', muted: '#A9A3BE', red: '#F87171', redBg: 'rgba(248,113,113,.16)',
  green: '#4ADE80', greenBg: 'rgba(74,222,128,.14)', amber: '#FBBF24', amberBg: 'rgba(251,191,36,.14)',
  hi: 'rgba(56,189,248,.10)', hiBorder: 'rgba(56,189,248,.55)', hiText: '#7DD3FC',
  shadow: '0 8px 30px rgba(0,0,0,.35)', blur: 'blur(14px)', glow: '0 0 38px -6px', tint: '26%',
  pageBg: 'radial-gradient(circle at 6% 94%, rgba(236,72,153,.42), transparent 36%), radial-gradient(circle at 94% 8%, rgba(251,146,60,.42), transparent 36%), radial-gradient(circle at 97% 92%, rgba(34,197,94,.40), transparent 36%), radial-gradient(circle at 55% 45%, rgba(250,204,21,.10), transparent 45%), radial-gradient(circle at 35% 10%, rgba(139,92,246,.14), transparent 40%), #07060C fixed',
  side: 'rgba(255,255,255,.03)', sideText: '#D8D2EA', sideMuted: '#8E88A6', sideActive: 'rgba(244,114,182,.20)', sideActiveText: '#FFFFFF',
  sideBorder: 'rgba(255,255,255,.08)', sideHoverText: '#FFFFFF', sideHoverBg: 'rgba(255,255,255,.06)', antdSurface: '#16131F',
  arFg: '#FFB443', arBg: 'rgba(255,170,40,.18)', apFg: '#E879F9', apBg: 'rgba(232,121,249,.18)', wrFg: '#4AE38A', wrBg: 'rgba(74,227,138,.16)',
  fyiFg: '#CBD5E1', fyiBg: 'rgba(148,163,184,.16)',
  dark: true,
}

// Blue Water: a clear tech-maritime blue-black, built for reading like GitHub Dark or Linear:
// cards one clear step lighter than the page, solid visible borders, bright body text and a
// light grey-blue for secondary text; a bright blue accent; no glow
const BLUEWATER: Palette = {
  accent: '#4C9AFF', accentBg: 'rgba(76,154,255,.18)', bg: '#0A1323', surface: '#13203A', surface2: '#1A2A48',
  border: '#2B3D5E', text: '#F2F6FC', muted: '#A9B9D2', red: '#FF8585', redBg: 'rgba(255,120,120,.16)',
  green: '#5BE3A5', greenBg: 'rgba(91,227,165,.15)', amber: '#FFC06E', amberBg: 'rgba(255,180,80,.16)',
  hi: 'rgba(76,154,255,.16)', hiBorder: '#5AA5FF', hiText: '#B5D5FF',
  shadow: '0 2px 10px rgba(0,0,0,.35)', blur: 'none', glow: '0 0 0 0', tint: '6%',
  pageBg: 'linear-gradient(180deg, #0C1628 0%, #0A1323 50%, #08101E 100%) fixed',
  side: '#0E1930', sideText: '#D6E1F2', sideMuted: '#9AABC6', sideActive: 'rgba(76,154,255,.24)', sideActiveText: '#FFFFFF',
  sideBorder: '#22324F', sideHoverText: '#FFFFFF', sideHoverBg: 'rgba(255,255,255,.07)', antdSurface: '#13203A',
  arFg: '#FFC06E', arBg: 'rgba(255,180,80,.16)', apFg: '#C4B0FF', apBg: 'rgba(170,140,255,.18)', wrFg: '#6FD3FF', wrBg: 'rgba(90,205,255,.16)',
  fyiFg: '#BCC8DA', fyiBg: 'rgba(170,185,210,.16)',
  dark: true,
}

export const MODES: { id: ModeId; name: string; palette: Palette }[] = [
  { id: 'bluewater', name: 'Blue Water', palette: BLUEWATER },
  { id: 'light', name: 'Keep it light', palette: LIGHT },
  { id: 'maritime', name: 'Maritime Pro', palette: MARITIME },
  { id: 'sakura', name: 'Sakura Pink', palette: SAKURA },
  { id: 'neon', name: 'Neon Glow', palette: NEON },
]

const v = (name: string) => `var(--mm-${name})`

export const c = {
  font: "'IBM Plex Sans', system-ui, sans-serif",
  mono: "'IBM Plex Mono', monospace",
  accent: v('accent'),
  accentBg: v('accentBg'),
  bg: v('bg'),
  surface: v('surface'),
  surface2: v('surface2'),
  border: v('border'),
  text: v('text'),
  muted: v('muted'),
  red: v('red'),
  redBg: v('redBg'),
  green: v('green'),
  greenBg: v('greenBg'),
  amber: v('amber'),
  amberBg: v('amberBg'),
  // priority 4 and 5 shading (U1)
  hi: v('hi'),
  hiBorder: v('hiBorder'),
  hiText: v('hiText'),
  shadow: v('shadow'),
  blur: v('blur'),
  glow: v('glow'),
  tint: v('tint'),
  side: v('side'),
  sideText: v('sideText'),
  sideMuted: v('sideMuted'),
  sideBorder: v('sideBorder'),
} as const

const paletteOf = (mode: ModeId) => (MODES.find((m) => m.id === mode) ?? MODES[0]).palette

/** Put the mode's palette on the page root (all `var(--mm-…)` values change at once). */
export function applyMode(mode: ModeId) {
  const p = paletteOf(mode)
  const root = document.documentElement
  for (const [k, value] of Object.entries(p)) {
    if (typeof value === 'string') root.style.setProperty(`--mm-${k}`, value)
  }
  root.dataset.mode = mode
  root.style.colorScheme = p.dark ? 'dark' : 'light'
  document.body.style.background = p.pageBg
}

/** The antd theme of a mode (antd derives hover and border shades from real colours). */
export function antdTheme(mode: ModeId): ThemeConfig {
  const p = paletteOf(mode)
  return {
    algorithm: p.dark ? antdAlgorithms.darkAlgorithm : antdAlgorithms.defaultAlgorithm,
    token: {
      fontFamily: c.font,
      fontFamilyCode: c.mono,
      colorPrimary: p.accent,
      colorLink: p.accent,
      colorBgLayout: p.bg,
      colorBgContainer: p.antdSurface,
      colorFillAlter: p.surface2,
      colorBorder: p.border,
      colorBorderSecondary: p.border,
      colorText: p.text,
      colorTextSecondary: p.muted,
      colorError: p.red,
      colorSuccess: p.green,
      colorWarning: p.amber,
      borderRadius: 8,
      borderRadiusLG: 12,
      fontSize: 14,
      lineHeight: 1.45,
    },
    components: {
      Layout: { siderBg: p.side, bodyBg: p.bg, headerBg: p.antdSurface },
      Menu: { itemSelectedBg: p.sideActive, itemSelectedColor: p.sideActiveText },
    },
  }
}

/** Sidebar colours of a mode, for the ProLayout token. */
export function sideTokens(mode: ModeId) {
  const p = paletteOf(mode)
  return {
    colorMenuBackground: p.side,
    colorBgMenuItemSelected: p.sideActive,
    colorTextMenuSelected: p.sideActiveText,
    colorTextMenu: p.sideText,
    colorTextMenuItemHover: p.sideHoverText,
    colorTextMenuTitle: p.sideText,
    colorTextMenuActive: p.sideActiveText,
    colorBgMenuItemHover: p.sideHoverBg,
    colorTextCollapsedButton: p.sideText,
  }
}

export type Pair = { fg: string; bg: string }

export const STATUS_COLORS: Record<NeedsAction, Pair> = {
  'Action Required': { fg: v('arFg'), bg: v('arBg') },
  'Approval Required': { fg: v('apFg'), bg: v('apBg') },
  'Waiting for Reply': { fg: v('wrFg'), bg: v('wrBg') },
  'FYI - No Action': { fg: v('fyiFg'), bg: v('fyiBg') },
  Close: { fg: v('green'), bg: v('greenBg') },
}

export const NOT_MATCHED: Pair = { fg: v('amber'), bg: v('amberBg') }
export const DONE: Pair = { fg: v('green'), bg: v('greenBg') }
export const LOW_PRIORITY: Pair = { fg: v('fyiFg'), bg: v('fyiBg') }
export const HIGH_PRIORITY: Pair = { fg: c.hiText, bg: c.hiBorder }

/** Background and border of a row, card or block at priority 4 or 5. */
export const HIGHLIGHT_STYLE = { background: c.hi, borderColor: c.hiBorder, boxShadow: `${c.glow} ${c.hiBorder}, ${c.shadow}` } as const

// the light palette is on the page before React starts, so the first paint has colours
applyMode(DEFAULT_MODE)
