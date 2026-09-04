import { FormEvent, useEffect, useState } from 'react'
import { apiMutation, invalidateQuery } from '../data/api'
import { useQuery } from '../hooks/useQuery'

type GroupStatus = {
  provider_id: string
  provider_name: string
  provider_enabled: boolean
  group_name: string
  group_enabled: boolean
  scan_batch_size: number
  backfill_days: number
  status: string
  checkpoint_article: number | null
  last_started_at: string | null
  last_completed_at: string | null
  last_error: string | null
  last_scanned_count: number
  last_indexed_count: number
}

type IndexerStatus = {
  enabled: boolean
  scan_interval_seconds: number
  scan_request_token: number
  groups: GroupStatus[]
}

const KEY = 'indexer-status'

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Never'
}

export default function IndexerPage() {
  const { data, loading, error, refresh } = useQuery<IndexerStatus>(KEY, '/api/indexer/status', { ttlMs: 1_000, refreshMs: 5_000 })
  const [enabled, setEnabled] = useState(true)
  const [interval, setIntervalValue] = useState('300')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    setEnabled(data.enabled)
    setIntervalValue(String(data.scan_interval_seconds))
  }, [data])

  const reload = async () => {
    invalidateQuery(KEY)
    await refresh()
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    const seconds = Number(interval)
    setBusy(true); setMessage(null); setActionError(null)
    try {
      await apiMutation('/api/indexer/settings', 'PATCH', { enabled, scan_interval_seconds: seconds })
      setMessage('Indexer settings saved.')
      await reload()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Could not save indexer settings')
    } finally { setBusy(false) }
  }

  const scanNow = async () => {
    setBusy(true); setMessage(null); setActionError(null)
    try {
      await apiMutation('/api/indexer/scan-now', 'POST')
      setMessage('Scan requested. The scanner worker will pick it up immediately.')
      await reload()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Could not request scan')
    } finally { setBusy(false) }
  }

  return (
    <section className="content route-page">
      <div className="page-heading"><div><small>Continuous NNTP scanner</small><h1>Indexer</h1><p>Durable scanner settings, checkpoints, and provider/group results.</p></div><button disabled={busy || !data?.enabled} onClick={() => void scanNow()}>Scan now</button></div>
      {error && <div className="inline-error">Could not load indexer status: {error}</div>}
      {actionError && <div className="inline-error">{actionError}</div>}
      {message && <div className="inline-success">{message}</div>}

      <section className="panel settings-panel">
        <div className="panel-title"><h3>Scanner</h3><span>{data?.enabled ? 'Enabled' : 'Disabled'}</span></div>
        <form className="inline-settings" onSubmit={save}>
          <label><span>Enabled</span><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /></label>
          <label><span>Interval (seconds)</span><input type="number" min="10" max="86400" value={interval} onChange={(event) => setIntervalValue(event.target.value)} /></label>
          <button disabled={busy} type="submit">Save</button>
        </form>
      </section>

      <section className="panel indexer-groups-panel">
        <div className="panel-title"><h3>Provider groups</h3><span>{data?.groups.length ?? 0}</span></div>
        {loading && !data ? <div className="loading-state">Loading indexer state…</div> : !data?.groups.length ? <div className="loading-state">No groups are configured. Add one under Settings.</div> : (
          <div className="indexer-table">
            <div className="indexer-row indexer-head"><span>Provider / group</span><span>Status</span><span>Checkpoint</span><span>Last scan</span><span>Result</span></div>
            {data.groups.map((group) => (
              <div className="indexer-row" key={`${group.provider_id}:${group.group_name}`}>
                <span><b>{group.provider_name}</b><small>{group.group_name}</small><small>batch {group.scan_batch_size} · backfill {group.backfill_days}d</small></span>
                <span><em className={`status-pill status-${group.status}`}>{!group.provider_enabled || !group.group_enabled ? 'disabled' : group.status}</em></span>
                <span>{group.checkpoint_article?.toLocaleString() ?? 'None'}</span>
                <span>{formatTime(group.last_completed_at)}</span>
                <span>{group.last_error ? <em className="error-text">{group.last_error}</em> : <>{group.last_scanned_count.toLocaleString()} headers<br /><small>{group.last_indexed_count.toLocaleString()} releases</small></>}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}
