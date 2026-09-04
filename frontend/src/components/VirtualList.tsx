import { ReactNode, useMemo, useState } from 'react'

type VirtualListProps<T> = {
  items: T[]
  height?: number
  rowHeight?: number
  overscan?: number
  getKey: (item: T) => string
  renderItem: (item: T) => ReactNode
}

export default function VirtualList<T>({
  items,
  height = 520,
  rowHeight = 68,
  overscan = 4,
  getKey,
  renderItem,
}: VirtualListProps<T>) {
  const [scrollTop, setScrollTop] = useState(0)
  const range = useMemo(() => {
    const visible = Math.ceil(height / rowHeight)
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan)
    const end = Math.min(items.length, start + visible + overscan * 2)
    return { start, end }
  }, [height, items.length, overscan, rowHeight, scrollTop])

  const visibleItems = items.slice(range.start, range.end)

  return (
    <div className="virtual-list" style={{ height }} onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
      <div className="virtual-list-space" style={{ height: items.length * rowHeight }}>
        <div style={{ transform: `translateY(${range.start * rowHeight}px)` }}>
          {visibleItems.map((item) => (
            <div className="virtual-row" style={{ height: rowHeight }} key={getKey(item)}>
              {renderItem(item)}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
