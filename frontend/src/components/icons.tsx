// Maritime icons (stroke SVG, currentColor) for the sidebar and the logo; @ant-design/icons has
// no ship or anchor. Wrapped in antd's Icon so they size and align like the built-in icons.
import Icon from '@ant-design/icons'
import type { GetProps } from 'antd'

type IconProps = Partial<GetProps<typeof Icon>>

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

const ShipSvg = () => (
  <svg width="1em" height="1em" viewBox="0 0 24 24" {...stroke} aria-hidden="true">
    <path d="M4 14l1.6 4.2c.2.5.7.8 1.2.8h10.4c.5 0 1-.3 1.2-.8L20 14z" />
    <path d="M6 14V9h12v5" />
    <path d="M9 9V6h4v3" />
    <path d="M15 9V7" />
    <path d="M2 21c1.5 0 1.5-1 3-1s1.5 1 3 1 1.5-1 3-1 1.5 1 3 1 1.5-1 3-1 1.5 1 3 1" />
  </svg>
)

const AnchorSvg = () => (
  <svg width="1em" height="1em" viewBox="0 0 24 24" {...stroke} aria-hidden="true">
    <circle cx="12" cy="5" r="2" />
    <path d="M12 7v14" />
    <path d="M8 11h8" />
    <path d="M4 14c0 4 3.6 7 8 7s8-3 8-7" />
    <path d="M4 14l-1.5 1.5M4 14l1.5 1.5M20 14l-1.5 1.5M20 14l1.5 1.5" />
  </svg>
)

export const ShipIcon = (props: IconProps) => <Icon component={ShipSvg} {...props} />
export const AnchorIcon = (props: IconProps) => <Icon component={AnchorSvg} {...props} />
