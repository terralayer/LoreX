import { FormEvent, lazy, Suspense, useEffect, useMemo, useState } from 'react'

const HomePage = lazy(() => import('./routes/HomePage'))
const LibraryPage = lazy(() => import('./routes/LibraryPage'))
const SearchPage = lazy(() => import('./routes/SearchPage'))

const nav = [
  { label: 'Home', route: '/' },
  { label: 'Wanted' },
  { label: 'Downloads' },
  { label: 'Library', route: '/library' },
  { label: 'Authors' },
  { label: 'Series' },
  { label: 'Narrators' },
  { label: 'Indexer' },
  { label: 'Activity' },
  { label: 'Settings' },
]

type Route = { path: string; query: URLSearchParams }

function readRoute(): Route {
  const raw = window.location.hash.replace(/^#/, '') || '/'
  const [path, query = ''] = raw.split('?')
  return { path: path || '/', query: new URLSearchParams(query) }
}

function Logo() {
  return (
    <div className="logo" aria-label="LoreX">
      <span className="logo-mark"><span className="book">⌄</span><span className="phones">∩</span></span>
      <span className="logo-text">Lore<span>X</span></span>
    </div>
  )
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => readRoute())
  const [globalSearch, setGlobalSearch] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    const onHash = () => {
      setRoute(readRoute())
      setSidebarOpen(false)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const activeRoute = route.path === '/search' ? '/search' : route.path
  const content = useMemo(() => {
    if (route.path === '/library') return <LibraryPage />
    if (route.path === '/search') return <SearchPage initialQuery={route.query.get('q') ?? ''} />
    return <HomePage />
  }, [route])

  const submitSearch = (event: FormEvent) => {
    event.preventDefault()
    const query = globalSearch.trim()
    if (!query) return
    window.location.hash = `/search?q=${encodeURIComponent(query)}`
  }

  return (
    <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <aside className="sidebar">
        <Logo />
        <nav>
          {nav.map((item, index) => (
            <button
              key={item.label}
              className={item.route && activeRoute === item.route ? 'active' : ''}
              disabled={!item.route}
              onClick={() => { if (item.route) window.location.hash = item.route }}
            >
              <span className="nav-dot">{index === 0 ? '⌂' : '·'}</span>{item.label}
              {item.label === 'Wanted' && <em>17</em>}
            </button>
          ))}
        </nav>
        <div className="system">
          <h4>System</h4>
          <p><span>Indexer</span><b className="ok">● Running</b></p>
          <p><span>API reads</span><b className="ok">● Bounded</b></p>
          <p><span>Search</span><b>&lt;150ms target</b></p>
          <div className="mini-progress"><i /></div>
          <p><span>Metadata cache</span><b className="ok">Coalesced</b></p>
        </div>
        <div className="sidebar-foot">Light <span>v0.1.1 alpha</span></div>
      </aside>

      <main>
        <header>
          <button className="menu" onClick={() => setSidebarOpen((value) => !value)} aria-label="Toggle navigation">☰</button>
          <form className="search search-form" onSubmit={submitSearch}>
            <input value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} placeholder="Search books, authors, series, or narrators…" aria-label="Global search" />
            <button aria-label="Search">⌕</button>
          </form>
          <div className="header-right"><span>⌁ Activity</span><span className="bell">♧<i>3</i></span><span className="avatar">TU</span></div>
        </header>
        <Suspense fallback={<div className="route-loading">Loading view…</div>}>{content}</Suspense>
      </main>
      {sidebarOpen && <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}
    </div>
  )
}
