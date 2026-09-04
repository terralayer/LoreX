import { useEffect, useMemo, useState } from 'react'
import VirtualList from '../components/VirtualList'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useQuery } from '../hooks/useQuery'

type Release = {
  id: string
  title: string
  author: string
  narrator: string | null
  format: string
  size: number
  completion: number
  download_status: string | null
  import_status: string | null
  posted_at: string | null
}

type SearchResponse = {
  total: number
  limit: number
  offset: number
  results: Release[]
}

type SearchPageProps = { initialQuery?: string }
const PAGE_SIZE = 50

function formatBytes(bytes: number) {
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

export default function SearchPage({ initialQuery = '' }: SearchPageProps) {
  const [query, setQuery] = useState(initialQuery)
  const [format, setFormat] = useState('')
  const [offset, setOffset] = useState(0)
  const debounced = useDebouncedValue(query, 250)

  useEffect(() => setOffset(0), [debounced, format])
  useEffect(() => setQuery(initialQuery), [initialQuery])

  const url = useMemo(() => {
    const params = new URLSearchParams({ q: debounced, limit: String(PAGE_SIZE), offset: String(offset), sort: 'title', order: 'asc' })
    if (format) params.set('format', format)
    return `/api/releases/search?${params.toString()}`
  }, [debounced, format, offset])

  const key = `release-search:${debounced}:${format}:${offset}`
  const { data, loading, error } = useQuery<SearchResponse>(key, url, { ttlMs: 20_000, enabled: debounced.trim().length > 0 })
  const results = data?.results ?? []
  const total = data?.total ?? 0
  const page = Math.floor(offset / PAGE_SIZE) + 1
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <section className="content route-page">
      <div className="page-heading"><div><small>Indexed audiobooks</small><h1>Search</h1><p>Debounced queries · PostgreSQL pagination</p></div></div>
      <div className="list-panel">
        <div className="list-toolbar">
          <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, author, narrator…" aria-label="Search releases" />
          <select value={format} onChange={(event) => setFormat(event.target.value)} aria-label="Filter format">
            <option value="">All formats</option><option value="m4b">M4B</option><option value="m4a">M4A</option><option value="mp3">MP3</option><option value="flac">FLAC</option><option value="aac">AAC</option>
          </select>
        </div>
        {!debounced.trim() ? <div className="loading-state">Type a title, author, or narrator to search.</div> : error ? <div className="inline-error">Search could not be refreshed.</div> : loading && results.length === 0 ? <div className="loading-state">Searching…</div> : results.length === 0 ? <div className="loading-state">No indexed releases matched.</div> : (
          <VirtualList
            items={results}
            height={Math.min(560, Math.max(180, results.length * 68))}
            getKey={(release) => release.id}
            renderItem={(release) => (
              <article className="catalog-row">
                <span className="catalog-mark">Lx</span>
                <div className="catalog-main"><b>{release.title}</b><p>{release.author}{release.narrator ? ` · ${release.narrator}` : ''}</p></div>
                <span className="format-pill">{release.format.toUpperCase()}</span>
                <span className="catalog-size">{formatBytes(release.size)}</span>
              </article>
            )}
          />
        )}
        {debounced.trim() && <div className="pager">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <span>{total.toLocaleString()} matches · Page {page} of {pages}</span>
          <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </div>}
      </div>
    </section>
  )
}
