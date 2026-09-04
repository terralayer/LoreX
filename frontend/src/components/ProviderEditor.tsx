import { FormEvent, useState } from 'react'

export type ProviderGroup = {
  group_name: string
  enabled: boolean
  scan_batch_size: number
  backfill_days: number
}

export type Provider = {
  id: string
  name: string
  host: string
  port: number
  enabled: boolean
  priority: number
  fill_server: boolean
  max_connections: number
  username_configured: boolean
  password_configured: boolean
  groups: ProviderGroup[]
}

export type ProviderSavePayload = {
  name: string
  host: string
  port: number
  enabled: boolean
  priority: number
  fill_server: boolean
  max_connections: number
  username?: string
  password?: string
  groups: ProviderGroup[]
}

type Props = {
  provider?: Provider | null
  busy?: boolean
  onSave: (payload: ProviderSavePayload) => Promise<void> | void
  onCancel: () => void
}

const defaultGroup: ProviderGroup = {
  group_name: 'alt.binaries.audiobooks',
  enabled: true,
  scan_batch_size: 5000,
  backfill_days: 0,
}

export default function ProviderEditor({ provider, busy = false, onSave, onCancel }: Props) {
  const [name, setName] = useState(provider?.name ?? 'Astraweb')
  const [host, setHost] = useState(provider?.host ?? 'news.astraweb.com')
  const [port, setPort] = useState(provider?.port ?? 563)
  const [enabled, setEnabled] = useState(provider?.enabled ?? true)
  const [priority, setPriority] = useState(provider?.priority ?? 100)
  const [fillServer, setFillServer] = useState(provider?.fill_server ?? false)
  const [maxConnections, setMaxConnections] = useState(provider?.max_connections ?? 4)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [groups, setGroups] = useState<ProviderGroup[]>(provider?.groups.length ? provider.groups : [defaultGroup])

  const updateGroup = (index: number, patch: Partial<ProviderGroup>) => {
    setGroups((current) => current.map((group, groupIndex) => groupIndex === index ? { ...group, ...patch } : group))
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const payload: ProviderSavePayload = {
      name: name.trim(),
      host: host.trim(),
      port,
      enabled,
      priority,
      fill_server: fillServer,
      max_connections: maxConnections,
      groups: groups.map((group) => ({ ...group, group_name: group.group_name.trim() })).filter((group) => group.group_name),
    }
    if (username) payload.username = username
    if (password) payload.password = password
    await onSave(payload)
  }

  return (
    <form className="panel provider-editor" onSubmit={submit}>
      <div className="panel-title"><h3>{provider ? `Edit ${provider.name}` : 'Add provider'}</h3></div>
      <div className="settings-grid">
        <label>Name<input required value={name} onChange={(event) => setName(event.target.value)} /></label>
        <label>Host<input required value={host} onChange={(event) => setHost(event.target.value)} /></label>
        <label>TLS port<input type="number" min={1} max={65535} value={port} onChange={(event) => setPort(Number(event.target.value))} /></label>
        <label>Priority<input type="number" value={priority} onChange={(event) => setPriority(Number(event.target.value))} /></label>
        <label>Max connections<input type="number" min={1} max={64} value={maxConnections} onChange={(event) => setMaxConnections(Number(event.target.value))} /></label>
        <label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder={provider?.username_configured ? 'Stored — leave blank to keep' : ''} /></label>
        <label>Password<input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={provider?.password_configured ? 'Stored — leave blank to keep' : ''} /></label>
      </div>
      <div className="settings-checks">
        <label><input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} /> Enabled</label>
        <label><input type="checkbox" checked={fillServer} onChange={(event) => setFillServer(event.target.checked)} /> Fill server</label>
      </div>

      <div className="panel-title"><h3>Newsgroups</h3><button type="button" onClick={() => setGroups((current) => [...current, { ...defaultGroup }])}>Add group</button></div>
      <div className="provider-groups">
        {groups.map((group, index) => (
          <div className="provider-group-row" key={`${index}-${group.group_name}`}>
            <input aria-label={`Group ${index + 1}`} value={group.group_name} onChange={(event) => updateGroup(index, { group_name: event.target.value })} />
            <label><input type="checkbox" checked={group.enabled} onChange={(event) => updateGroup(index, { enabled: event.target.checked })} /> Scan</label>
            <label>Batch <input type="number" min={100} max={50000} value={group.scan_batch_size} onChange={(event) => updateGroup(index, { scan_batch_size: Number(event.target.value) })} /></label>
            <label>Backfill days <input type="number" min={0} max={10000} value={group.backfill_days} onChange={(event) => updateGroup(index, { backfill_days: Number(event.target.value) })} /></label>
            <button type="button" disabled={groups.length === 1} onClick={() => setGroups((current) => current.filter((_, groupIndex) => groupIndex !== index))}>Remove</button>
          </div>
        ))}
      </div>
      <div className="form-actions">
        <button type="button" onClick={onCancel}>Cancel</button>
        <button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save provider'}</button>
      </div>
    </form>
  )
}
