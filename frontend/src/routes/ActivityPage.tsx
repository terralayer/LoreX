import { useQuery } from '../hooks/useQuery'

type ActivityEvent = {
  id: number
  kind: string
  entity_id: string | null
  message: string
  detail: string | null
  created_at: string
}

type ActivityList = { count: number; events: ActivityEvent[] }

function icon(kind: string) {
  if (kind === 'download') return '↓'
  if (kind === 'scanner') return '⌁'
  if (kind === 'import') return '✓'
  return '·'
}

export default function ActivityPage() {
  const { data, loading, error, refresh } = useQuery<ActivityList>('activity', '/api/activity?limit=100', { ttlMs: 1_000, refreshMs: 5_000 })

  return (
    <section className="content route-page">
      <div className="page-heading"><div><small>Durable operational events</small><h1>Activity</h1><p>Scanner, download, and import events recorded by the backend. No synthetic entries.</p></div><button onClick={() => void refresh()}>Refresh</button></div>
      {error && <div className="inline-error">Could not load activity: {error}</div>}
      <section className="panel activity-panel">
        <div className="panel-title"><h3>Recent activity</h3><span>{data?.count ?? 0}</span></div>
        {loading && !data ? <div className="loading-state">Loading activity…</div> : !data?.events.length ? <div className="loading-state">No activity has been recorded yet.</div> : data.events.map((event) => (
          <article className="activity activity-full" key={event.id}>
            <span>{icon(event.kind)}</span>
            <div><p><b>{event.message}</b></p>{event.detail && <small>{event.detail}</small>}<small>{event.kind}{event.entity_id ? ` · ${event.entity_id}` : ''}</small></div>
            <time>{new Date(event.created_at).toLocaleString()}</time>
          </article>
        ))}
      </section>
    </section>
  )
}
