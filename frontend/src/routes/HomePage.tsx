import { useQuery } from '../hooks/useQuery'

type Dashboard = {
  library_books: number
  total_releases: number
  active_downloads: number
  queued_downloads: number
}

export default function HomePage() {
  const { data, loading, error } = useQuery<Dashboard>('dashboard', '/api/dashboard', {
    ttlMs: 5_000,
    refreshMs: 10_000,
  })

  const number = (value: number | undefined) => value === undefined ? '—' : value.toLocaleString()

  return (
    <section className="content route-page" aria-busy={loading}>
      {error && <div className="inline-error">LoreX could not refresh live dashboard data.</div>}
      <div className="page-heading">
        <div><small>Live system state</small><h1>Home</h1><p>No demo releases, fake speeds, or placeholder activity.</p></div>
      </div>
      <div className="metrics">
        <Metric icon="▣" label="Library" value={number(data?.library_books)} sub="books" note="Persisted library" />
        <Metric icon="⇩" label="Downloading" value={number(data?.active_downloads)} sub="active" note={`${number(data?.queued_downloads)} queued`} />
        <Metric icon="◉" label="Indexed" value={number(data?.total_releases)} sub="audiobooks" note="PostgreSQL indexed" />
        <Metric icon="◷" label="API" value={data ? 'Healthy' : loading ? 'Loading' : 'Offline'} sub="service status" note="Live API response" good={Boolean(data)} />
      </div>
      <section className="panel">
        <div className="panel-title"><h3>Production status</h3></div>
        <div className="loading-state">
          {data?.total_releases
            ? 'Search the indexed releases to inspect the real database.'
            : 'No indexed releases yet. Configure a Usenet provider and run the indexer.'}
        </div>
      </section>
    </section>
  )
}

function Metric({ icon, label, value, sub, note, good }: { icon:string; label:string; value:string; sub:string; note:string; good?:boolean }) {
  return <div className="metric"><span className="metric-icon">{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{sub}</p><em className={good ? 'green' : ''}>{note}</em></div></div>
}
