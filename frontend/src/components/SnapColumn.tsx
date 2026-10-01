// A scrolling column as tall as its row, cut at the last whole item, so no card is shown half
// (Email page list). Items are the children of the first child element.
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export function SnapColumn({ children, minHeight }: { children: ReactNode; minHeight: string }) {
  const outer = useRef<HTMLDivElement>(null)
  const inner = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState<number | null>(null)

  useLayoutEffect(() => {
    const box = outer.current
    const scroller = inner.current
    if (!box || !scroller) return
    const fit = () => {
      const limit = box.clientHeight
      const items = Array.from((scroller.firstElementChild?.children ?? []) as HTMLCollectionOf<HTMLElement>)
      let bottom = 0
      for (const item of items) {
        const end = item.offsetTop + item.offsetHeight
        if (end > limit) break
        bottom = end
      }
      setHeight(bottom > 0 && bottom < limit ? bottom + 2 : null)
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(box)
    if (scroller.firstElementChild) observer.observe(scroller.firstElementChild)
    return () => observer.disconnect()
  }, [children])

  return (
    <div ref={outer} style={{ width: 372, flexShrink: 0, position: 'relative', minHeight }}>
      <div ref={inner} style={{ position: 'absolute', top: 0, left: 0, right: 0, height: height ?? '100%', overflowY: 'auto', paddingRight: 4 }}>
        {children}
      </div>
    </div>
  )
}
