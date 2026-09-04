import { FormEvent, lazy, Suspense, useEffect, useMemo, useState } from 'react'

const HomePage = lazy(() => import('./routes/HomePage'))
const LibraryPage = lazy(() => import('./routes/LibraryPage'))
const SearchPage = lazy(() => import('./routes/SearchPage'))

const nav = [
  { label: 'Home', route: '/' },
  { label: 'Library', route: '/library' },
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
              className={activeRoute === item.route ? 'active' : ''}
              onClick={() => { window.location.hash = item.route }}
            >
              <span className="nav-dot">{index === 0 ? '⌂' : '·'}</span>{item.label}
            </button>
          ))}
        </nav>
        <div className="system">
          <h4>LoreX</h4>
          <p><span>Mode</span><b>Live data only</b></p>
          <p><span>Version</span><b>0.1.1 alpha</b></p>
        </div>
        <div className="sidebar-foot">Light <span>v0.1.1 alpha</span></div>
      </aside>

      <main>
        <header>
          <button className="menu" onClick={() => setSidebarOpen((value) => !value)} aria-label="Toggle navigation">☰</button>
          <form className="search search-form" onSubmit={submitSearch}>
            <input value={globalSearch} onChange={(event) => setGlobalSearch(event.target.value)} placeholder="Search indexed audiobooks…" aria-label="Global search" />
            <button aria-label="Search">⌕</button>
          </form>
          <div className="header-right"><span>LoreX</span></div>
        </header>
        <Suspense fallback={<div className="route-loading">Loading view…</div>}>{content}</Suspense>
      </main>
      {sidebarOpen && <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}
    </div>
  )
}
