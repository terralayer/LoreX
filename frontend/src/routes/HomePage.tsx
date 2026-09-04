import { useQuery } from '../hooks/useQuery'

type ProviderHealth = {
  provider: string
  attempts: number
  successes: number
  failures: number
  fallbacks: number
  bytes_delivered: number
  elapsed_ms_total: number
  success_rate: number | null
  throughput_mib_s: number | null
}

type RecentRelease = { id: string; title: string; author: string; narrator: string | null; format: string; size: number; completion: number; download_status: string | null; import_status: string | null; posted_at: string | null }
type RecentDownload = { id: string; status: string; title: string | null; author: string | null; bytes_completed: number; release_size: number | null; updated_at: string }
type Activity = { id: number; kind: string; message: string; detail: string | null; created_at: string }
type SystemSummary = {
  ready: boolean
  configuration_issues: string[]
  credential_key_available: boolean
  providers_configured: number
  providers_enabled: number
  groups_enabled: number
  library_books: number
  total_releases: number
  downloads: Record<string, number>
  scanner_enabled: boolean
  scan_interval_seconds: number | null
  scanner_groups_scanning: number
  scanner_groups_error: number
  provider_health: ProviderHealth[]
  recent_releases: RecentRelease[]
  recent_downloads: RecentDownload[]
  recent_activity: Activity[]
}

const ACTIVE = ['queued', 'downloading', 'postprocessing', 'importing']

export default function HomePage() {
  const { data, loading, error, refresh } = useQuery<SystemSummary>('system-summary', '/api/system/summary', { ttlMs: 2_000, refreshMs: 10_000 })
  const number = (value: number | undefined) => value === undefined ? '—' : value.toLocaleString()
  const activeDownloads = data ? ACTIVE.reduce((sum, status) => sum + (data.downloads[status] ?? 0), 0) : undefined

  return (
    <section className="content route-page" aria-busy={loading}>
      {error && <div className="inline-error">LoreX could not refresh live system state: {error}</div>}
      <div className="page-heading">
        <div><small>Live system state</small><h1>Home</h1><p>Every count and health value below comes from persisted LoreX state.</p></div>
        <button onClick={() => void refresh()}>Refresh</button>
      </div>

      <div className="metrics">
        <Metric icon="▣" label="Library" value={number(data?.library_books)} sub="physical imports" note="Persisted books" />
        <Metric icon="◉" label="Indexed" value={number(data?.total_releases)} sub="releases" note="PostgreSQL index" />
        <Metric icon="⇩" label="Downloads" value={number(activeDownloads)} sub="active / queued" note={`${number(data?.downloads.failed)} failed`} />
        <Metric icon="⌁" label="Indexer" value={data ? data.scanner_enabled ? 'Running' : 'Stopped' : '—'} sub={data?.scan_interval_seconds ? `every ${data.scan_interval_seconds}s` : 'not available'} note={data?.scanner_groups_error ? `${data.scanner_groups_error} group errors` : 'No recorded group errors'} good={Boolean(data?.scanner_enabled && !data?.scanner_groups_error)} />
        <Metric icon="◎" label="Providers" value={number(data?.providers_enabled)} sub={`${number(data?.groups_enabled)} enabled groups`} note={`${number(data?.providers_configured)} configured`} good={Boolean(data?.ready)} />
      </div>

      {data && !data.ready && <section className="panel onboarding-panel">
        <div className="panel-title"><h3>Configuration required</h3><span>Not ready</span></div>
        <div className="onboarding-body">
          <div>{data.configuration_issues.map((issue) => <p key={issue}>{issue}</p>)}</div>
          <button onClick={() => { window.location.hash = '/settings' }}>Open Settings</button>
        </div>
      </section>}

      <div className="dashboard-grid live-dashboard-grid">
        <section className="panel">
          <div className="panel-title"><h3>Provider health</h3><span>{data?.provider_health.length ?? 0}</span></div>
          {!data?.provider_health.length ? <div className="loading-state">No provider health measurements yet.</div> : data.provider_health.map((provider) => (
            <div className="provider-health" key={provider.provider}>
              <div><b>{provider.provider}</b><small>{provider.attempts.toLocaleString()} attempts · {provider.failures.toLocaleString()} failures · {provider.fallbacks.toLocaleString()} fallbacks</small></div>
              <span>{provider.success_rate === null ? 'Not measured' : `${(provider.success_rate * 100).toFixed(1)}% success`}</span>
              <span>{provider.throughput_mib_s === null ? 'Speed not measured' : `${provider.throughput_mib_s.toFixed(1)} MiB/s measured`}</span>
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="panel-title"><h3>Recent indexed releases</h3><button className="text-button" onClick={() => { window.location.hash = '/search' }}>Search</button></div>
          {!data?.recent_releases.length ? <div className="loading-state">No releases indexed yet.</div> : data.recent_releases.map((release) => (
            <div className="release live-release" key={release.id}><span className="catalog-mark">Lx</span><div><b>{release.title}</b><p>{release.author}{release.narrator ? ` · ${release.narrator}` : ''}</p><small>{release.format.toUpperCase()}</small></div><time>{release.download_status ?? 'indexed'}</time></div>
          ))}
        </section>

        <section className="panel">
          <div className="panel-title"><h3>Recent activity</h3><button className="text-button" onClick={() => { window.location.hash = '/activity' }}>All activity</button></div>
          {!data?.recent_activity.length ? <div className="loading-state">No activity recorded yet.</div> : data.recent_activity.map((event) => (
            <div className="activity" key={event.id}><span>{event.kind === 'download' ? '↓' : event.kind === 'scanner' ? '⌁' : '·'}</span><div><p>{event.message}</p>{event.detail && <small>{event.detail}</small>}</div><time>{new Date(event.created_at).toLocaleTimeString()}</time></div>
          ))}
        </section>
      </div>
    </section>
  )
}

function Metric({ icon, label, value, sub, note, good }: { icon:string; label:string; value:string; sub:string; note:string; good?:boolean }) {
  return <div className="metric"><span className="metric-icon">{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{sub}</p><em className={good ? 'green' : ''}>{note}</em></div></div>
}
