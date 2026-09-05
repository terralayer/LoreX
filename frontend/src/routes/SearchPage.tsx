import { useState } from 'react'
import VirtualList from '../components/VirtualList'
import { apiMutation, invalidateQuery } from '../data/api'

type Release = {
  id: string
  title: string
  author: string
  narrator: string | null
  format: string
  size: number
  completion: number
  nzb: string
  source_subject: string
}

type SmartResult = {
  score: number
  bucket: 'likely' | 'possible'
  reasons: string[]
  release: Release
}

type SmartSearchResponse = {
  queries: string[]
  stopped_early: boolean
  results: SmartResult[]
}

type GrabResponse = { id: string; release_id: string; status: string }
type SearchPageProps = { initialQuery?: string }

function formatBytes(bytes: number) {
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

export default function SearchPage({ initialQuery = '' }: SearchPageProps) {
  const [title, setTitle] = useState(initialQuery)
  const [author, setAuthor] = useState('')
  const [results, setResults] = useState<SmartResult[]>([])
  const [queries, setQueries] = useState<string[]>([])
  const [stoppedEarly, setStoppedEarly] = useState(false)
  const [searching, setSearching] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)

  const search = async () => {
    const cleanTitle = title.trim()
    if (!cleanTitle) return
    setSearching(true)
    setActionError(null)
    setSearched(true)
    try {
      const response = await apiMutation<SmartSearchResponse>('/api/search/on-demand', 'POST', {
        title: cleanTitle,
        author: author.trim() || null,
        stop_score: 95,
      })
      setResults(response.results)
      setQueries(response.queries)
      setStoppedEarly(response.stopped_early)
    } catch (caught) {
      setResults([])
      setQueries([])
      setActionError(caught instanceof Error ? caught.message : 'Search failed')
    } finally {
      setSearching(false)
    }
  }

  const grab = async (release: Release) => {
    setBusyId(release.id)
    setActionError(null)
    try {
      await apiMutation<GrabResponse>(`/api/releases/${release.id}/grab`, 'POST')
      invalidateQuery('downloads')
      invalidateQuery('system-summary')
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Could not queue download')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="content route-page">
      <div className="page-heading">
        <div>
          <small>On-demand audiobook search</small>
          <h1>Search</h1>
          <p>LoreX expands one book request into focused audiobook queries, ranks likely matches, and stops once it finds a strong result.</p>
        </div>
      </div>
      {actionError && <div className="inline-error">{actionError}</div>}
      <div className="list-panel">
        <div className="list-toolbar smart-search-toolbar">
          <input
            autoFocus
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') void search() }}
            placeholder="Book title"
            aria-label="Book title"
          />
          <input
            value={author}
            onChange={(event) => setAuthor(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') void search() }}
            placeholder="Author (optional)"
            aria-label="Book author"
          />
          <button disabled={searching || !title.trim()} onClick={() => void search()}>
            {searching ? 'Searching…' : 'Search Audiobooks'}
          </button>
        </div>
        {queries.length > 0 && (
          <div className="search-summary">
            Tried {queries.length} focused {queries.length === 1 ? 'query' : 'queries'}{stoppedEarly ? ' · stopped after a strong match' : ''}.
          </div>
        )}
        {!searched ? (
          <div className="loading-state">Enter the audiobook you want. LoreX will search only when you tell it to.</div>
        ) : searching && results.length === 0 ? (
          <div className="loading-state">Expanding title and author variants and scoring matches…</div>
        ) : results.length === 0 ? (
          <div className="loading-state">No plausible audiobook matches found.</div>
        ) : (
          <VirtualList
            items={results}
            height={Math.min(560, Math.max(180, results.length * 76))}
            getKey={(item) => item.release.id}
            renderItem={(item) => (
              <article className="catalog-row catalog-row-actions">
                <span className="catalog-mark">{item.score}</span>
                <div className="catalog-main">
                  <b>{item.release.title}</b>
                  <p>{item.release.author}{item.release.narrator ? ` · ${item.release.narrator}` : ''} · {item.bucket === 'likely' ? 'Likely match' : 'Possible match'}</p>
                </div>
                <span className="format-pill">{item.release.format.toUpperCase()}</span>
                <span className="catalog-size">{formatBytes(item.release.size)}</span>
                <span className="catalog-action">
                  <button disabled={busyId === item.release.id} onClick={() => void grab(item.release)}>
                    {busyId === item.release.id ? 'Queuing…' : 'Grab'}
                  </button>
                </span>
              </article>
            )}
          />
        )}
      </div>
    </section>
  )
}
