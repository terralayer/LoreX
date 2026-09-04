import { useState } from 'react'
import { apiMutation, invalidateQuery } from '../data/api'
import { useQuery } from '../hooks/useQuery'

type DownloadJob = {
  id: string
  release_id: string
  status: string
  bytes_completed: number
  articles_completed: number
  total_articles: number
  error: string | null
  cancel_requested: boolean
  completed_at: string | null
  updated_at: string
  title: string | null
  author: string | null
  release_size: number | null
}

type DownloadList = { count: number; downloads: DownloadJob[] }

const KEY = 'downloads'
const ACTIVE = new Set(['queued', 'downloading', 'postprocessing', 'importing'])

function formatBytes(value: number | null) {
  if (value === null) return '—'
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let index = 0
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1 }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`
}

function JobCard({ job, busy, onRetry, onCancel }: { job: DownloadJob; busy: boolean; onRetry: () => void; onCancel: () => void }) {
  const progress = job.release_size && job.release_size > 0
    ? Math.min(100, Math.max(0, (job.bytes_completed / job.release_size) * 100))
    : null
  const articleProgress = job.total_articles > 0 ? `${job.articles_completed}/${job.total_articles} articles` : 'Article count pending'
  return (
    <article className="job-card">
      <div className="job-top">
        <div><b>{job.title ?? job.release_id}</b><p>{job.author ?? 'Unknown author'} · {formatBytes(job.release_size)}</p></div>
        <em className={`status-pill status-${job.status}`}>{job.cancel_requested ? 'Cancel requested' : job.status}</em>
      </div>
      <div className="download-line">
        <div className="progress" aria-label="Download progress"><i style={{ width: `${progress ?? 0}%` }} /></div>
        <span>{progress === null ? articleProgress : `${progress.toFixed(1)}% · ${articleProgress}`}</span>
      </div>
      <div className="job-meta"><span>{formatBytes(job.bytes_completed)} received</span><span>Updated {new Date(job.updated_at).toLocaleString()}</span></div>
      {job.error && <div className="inline-error compact">{job.error}</div>}
      <div className="form-actions">
        {(job.status === 'failed' || job.status === 'canceled') && <button disabled={busy} onClick={onRetry}>Retry</button>}
        {ACTIVE.has(job.status) && <button disabled={busy || job.cancel_requested} onClick={onCancel}>{job.cancel_requested ? 'Cancel requested' : 'Cancel'}</button>}
      </div>
    </article>
  )
}

export default function DownloadsPage() {
  const { data, loading, error, refresh } = useQuery<DownloadList>(KEY, '/api/downloads?limit=200', { ttlMs: 1_000, refreshMs: 3_000 })
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const mutate = async (job: DownloadJob, action: 'retry' | 'cancel') => {
    setBusyId(job.id)
    setActionError(null)
    try {
      await apiMutation(`/api/downloads/${job.id}/${action}`, 'POST')
      invalidateQuery(KEY)
      await refresh()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Download action failed')
    } finally {
      setBusyId(null)
    }
  }

  const jobs = data?.downloads ?? []
  const active = jobs.filter((job) => ACTIVE.has(job.status))
  const failed = jobs.filter((job) => job.status === 'failed' || job.status === 'canceled')
  const completed = jobs.filter((job) => job.status === 'completed')

  const section = (title: string, rows: DownloadJob[], empty: string) => (
    <section className="panel downloads-panel">
      <div className="panel-title"><h3>{title}</h3><span>{rows.length}</span></div>
      {rows.length ? rows.map((job) => <JobCard key={job.id} job={job} busy={busyId === job.id} onRetry={() => void mutate(job, 'retry')} onCancel={() => void mutate(job, 'cancel')} />) : <div className="loading-state">{empty}</div>}
    </section>
  )

  return (
    <section className="content route-page">
      <div className="page-heading"><div><small>Automatic download worker</small><h1>Downloads</h1><p>Live queue state from PostgreSQL. Progress is reported only from persisted bytes and articles.</p></div><button onClick={() => void refresh()}>Refresh</button></div>
      {error && <div className="inline-error">Could not load downloads: {error}</div>}
      {actionError && <div className="inline-error">{actionError}</div>}
      {loading && !data ? <div className="loading-state">Loading downloads…</div> : <div className="route-grid">{section('Active', active, 'No active downloads.')}{section('Failed / canceled', failed, 'No failed downloads.')}{section('Completed', completed, 'No completed downloads yet.')}</div>}
    </section>
  )
}
