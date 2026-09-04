import { useEffect, useMemo, useState } from 'react'
import VirtualList from '../components/VirtualList'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useQuery } from '../hooks/useQuery'

type Book = {
  id: string
  title: string
  author: string
  narrator: string | null
  format: string
  size: number
}

type LibraryPageResponse = {
  total: number
  limit: number
  offset: number
  results: Book[]
}

const PAGE_SIZE = 50

function formatBytes(bytes: number) {
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

export default function LibraryPage() {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('title')
  const [order, setOrder] = useState('asc')
  const debounced = useDebouncedValue(query, 250)

  useEffect(() => setOffset(0), [debounced, sort, order])

  const url = useMemo(() => {
    const params = new URLSearchParams({
      q: debounced,
      limit: String(PAGE_SIZE),
      offset: String(offset),
      sort,
      order,
    })
    return `/api/library/books?${params.toString()}`
  }, [debounced, offset, order, sort])

  const key = `library:${debounced}:${offset}:${sort}:${order}`
  const { data, loading, error } = useQuery<LibraryPageResponse>(key, url, { ttlMs: 30_000 })
  const results = data?.results ?? []
  const total = data?.total ?? 0
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="content route-page">
      <div className="page-heading">
        <div><small>Managed collection</small><h1>Library</h1><p>{total.toLocaleString()} books · server paginated</p></div>
      </div>
      <div className="list-panel">
        <div className="list-toolbar">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter title, author, or narrator…" aria-label="Filter library" />
          <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort library">
            <option value="title">Title</option><option value="author">Author</option><option value="narrator">Narrator</option><option value="format">Format</option><option value="size">Size</option>
          </select>
          <select value={order} onChange={(event) => setOrder(event.target.value)} aria-label="Sort order"><option value="asc">Ascending</option><option value="desc">Descending</option></select>
        </div>
        {error && <div className="inline-error">Could not refresh this library page.</div>}
        {loading && results.length === 0 ? <div className="loading-state">Loading library…</div> : results.length === 0 ? <div className="loading-state">No books match this filter.</div> : (
          <VirtualList
            items={results}
            height={Math.min(560, Math.max(180, results.length * 68))}
            getKey={(book) => book.id}
            renderItem={(book) => (
              <article className="catalog-row">
                <span className="catalog-mark">Lx</span>
                <div className="catalog-main"><b>{book.title}</b><p>{book.author}{book.narrator ? ` · ${book.narrator}` : ''}</p></div>
                <span className="format-pill">{book.format.toUpperCase()}</span>
                <span className="catalog-size">{formatBytes(book.size)}</span>
              </article>
            )}
          />
        )}
        <div className="pager">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <span>Page {page} of {pages}</span>
          <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </div>
      </div>
    </section>
  )
}
