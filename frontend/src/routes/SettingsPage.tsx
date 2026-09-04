import { useState } from 'react'
import ProviderEditor, { Provider, ProviderSavePayload } from '../components/ProviderEditor'
import { apiMutation, invalidateQuery } from '../data/api'
import { useQuery } from '../hooks/useQuery'

type ProviderList = { count: number; providers: Provider[] }
type ProviderTest = { status: string; provider_id: string; group: string | null }

const KEY = 'nntp-providers'

export default function SettingsPage() {
  const { data, loading, error, refresh } = useQuery<ProviderList>(KEY, '/api/settings/nntp/providers', { ttlMs: 5_000 })
  const [editing, setEditing] = useState<Provider | null | undefined>(undefined)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const reload = async () => {
    invalidateQuery(KEY)
    await refresh()
  }

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setActionError(null)
    setMessage(null)
    try {
      await action()
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const save = async (payload: ProviderSavePayload) => {
    await run(async () => {
      if (editing) {
        await apiMutation(`/api/settings/nntp/providers/${editing.id}`, 'PATCH', payload)
      } else {
        await apiMutation('/api/settings/nntp/providers', 'POST', payload)
      }
      setEditing(undefined)
      setMessage('Provider saved.')
      await reload()
    })
  }

  const testProvider = async (provider: Provider) => {
    await run(async () => {
      const result = await apiMutation<ProviderTest>(`/api/settings/nntp/providers/${provider.id}/test`, 'POST')
      setMessage(result.group ? `${provider.name}: connected and opened ${result.group}.` : `${provider.name}: connected.`)
    })
  }

  const clearSecret = async (provider: Provider, field: 'username' | 'password') => {
    await run(async () => {
      await apiMutation(`/api/settings/nntp/providers/${provider.id}/credentials/${field}/clear`, 'POST')
      setMessage(`${provider.name}: ${field} cleared.`)
      await reload()
    })
  }

  const remove = async (provider: Provider) => {
    if (!window.confirm(`Delete provider ${provider.name}?`)) return
    await run(async () => {
      await apiMutation(`/api/settings/nntp/providers/${provider.id}`, 'DELETE')
      setMessage(`${provider.name} deleted.`)
      await reload()
    })
  }

  return (
    <section className="content route-page">
      <div className="page-heading">
        <div><small>Encrypted provider configuration</small><h1>Settings</h1><p>Usenet provider credentials are stored encrypted and are never returned to this page.</p></div>
        <button onClick={() => setEditing(null)} disabled={busy}>Add provider</button>
      </div>

      {error && <div className="inline-error">Could not load providers: {error}</div>}
      {actionError && <div className="inline-error">{actionError}</div>}
      {message && <div className="inline-success">{message}</div>}

      {editing !== undefined && <ProviderEditor provider={editing} busy={busy} onSave={save} onCancel={() => setEditing(undefined)} />}

      <section className="panel">
        <div className="panel-title"><h3>Usenet providers</h3><span>{data?.count ?? 0} configured</span></div>
        {loading && !data ? <div className="loading-state">Loading providers…</div> : !data?.providers.length ? (
          <div className="loading-state">No provider is configured. Add Astraweb or another TLS NNTP provider to begin indexing.</div>
        ) : (
          <div className="provider-settings-list">
            {data.providers.map((provider) => (
              <article className="provider-settings-card" key={provider.id}>
                <div className="provider-settings-main">
                  <div><b>{provider.name}</b><p>{provider.host}:{provider.port} · {provider.fill_server ? 'Fill' : 'Primary'} · priority {provider.priority}</p></div>
                  <em className={provider.enabled ? 'success' : 'warning'}>{provider.enabled ? 'Enabled' : 'Disabled'}</em>
                </div>
                <div className="provider-settings-meta">
                  <span>{provider.max_connections} connections</span>
                  <span>{provider.groups.filter((group) => group.enabled).length}/{provider.groups.length} groups enabled</span>
                  <span>User: {provider.username_configured ? 'stored' : 'not set'}</span>
                  <span>Password: {provider.password_configured ? 'stored' : 'not set'}</span>
                </div>
                <div className="provider-group-summary">
                  {provider.groups.map((group) => <span key={group.group_name}>{group.group_name} · batch {group.scan_batch_size} · backfill {group.backfill_days}d</span>)}
                </div>
                <div className="form-actions">
                  <button disabled={busy} onClick={() => void testProvider(provider)}>Test connection</button>
                  <button disabled={busy} onClick={() => setEditing(provider)}>Edit</button>
                  {provider.username_configured && <button disabled={busy} onClick={() => void clearSecret(provider, 'username')}>Clear username</button>}
                  {provider.password_configured && <button disabled={busy} onClick={() => void clearSecret(provider, 'password')}>Clear password</button>}
                  <button disabled={busy} onClick={() => void remove(provider)}>Delete</button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  )
}
