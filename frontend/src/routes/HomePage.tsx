import { useQuery } from '../hooks/useQuery'

type Dashboard = {
  library_books: number
  total_releases: number
  active_downloads: number
  queued_downloads: number
}

const recent = [
  ['Project Hail Mary', 'Andy Weir · Ray Porter', 'M4B', '1.20 GB'],
  ['The Will of the Many', 'James Islington · Euan Morton', 'M4B', '1.15 GB'],
  ['Dungeon Crawler Carl Book 6', 'Matt Dinniman · Jeff Hays', 'MP3', '980 MB'],
  ['Fourth Wing', 'Rebecca Yarros · Rebecca Soler', 'M4B', '1.05 GB'],
]

export default function HomePage() {
  const { data, loading, error } = useQuery<Dashboard>('dashboard', '/api/dashboard', {
    ttlMs: 5_000,
    refreshMs: 10_000,
  })

  const number = (value: number | undefined) => value === undefined ? '—' : value.toLocaleString()

  return (
    <section className="content route-page" aria-busy={loading}>
      {error && <div className="inline-error">Dashboard refresh failed. Cached data will be retained when available.</div>}
      <div className="metrics">
        <Metric icon="▣" label="Library" value={number(data?.library_books)} sub="books" note="Managed library" />
        <Metric icon="▱" label="Wanted" value="17" sub="books" note="3 found today" warn />
        <Metric icon="⇩" label="Downloading" value={number(data?.active_downloads)} sub="active" note={`${number(data?.queued_downloads)} queued`} />
        <Metric icon="◉" label="Indexed" value={number(data?.total_releases)} sub="audiobooks" note="PostgreSQL indexed" good />
        <Metric icon="◷" label="API" value={data ? 'Healthy' : loading ? 'Loading' : 'Offline'} sub="service status" note="10s coalesced refresh" good={Boolean(data)} />
      </div>

      <div className="dashboard-grid">
        <Panel title="Recent Releases" action="Search">
          <div className="release-list">{recent.map(([title, byline, format, size], i) => <ReleaseRow key={title} title={title} byline={byline} format={format} size={size} index={i} />)}</div>
        </Panel>

        <Panel title="Active Downloads" action="Downloads">
          <Download title="Project Hail Mary" pct={68} speed="34.2 MB/s" meta="812 MB / 1.20 GB · 03:41 ETA" />
          <Download title="The Will of the Many" pct={42} speed="28.7 MB/s" meta="486 MB / 1.15 GB · 04:02 ETA" />
          <Download title="The Martian" pct={12} speed="22.1 MB/s" meta="108 MB / 900 MB · 00:36 ETA" />
        </Panel>

        <Panel title="Wanted Matches" action="Wanted">
          <Wanted title="Mistborn: The Hero of Ages" author="Brandon Sanderson" status="Release Found" />
          <Wanted title="Cradle: Wintersteel" author="Will Wight" status="Release Found" />
          <Wanted title="The Stormlight Archive #5" author="Brandon Sanderson" status="Searching" warning />
          <Wanted title="Red Rising: Iron Gold" author="Pierce Brown" status="Missing" danger />
          <Wanted title="The Name of the Wind" author="Patrick Rothfuss" status="Missing" danger />
        </Panel>

        <Panel title="Indexer Status" action="Indexer">
          <Stat label="Status" value="Running" good />
          <Stat label="Current Group" value="alt.binaries.audio.audiobook" />
          <Stat label="Article" value="231,481,902" />
          <Stat label="Headers/sec" value="36,927" />
          <Stat label="Candidates" value="418" />
          <Stat label="Audiobooks" value="31" />
          <Stat label="Rejected Articles" value="299" />
        </Panel>

        <Panel title="Provider Health" action="Settings">
          <div className="provider-head"><span>Provider</span><span>Health</span><span>Speed</span><span>Status</span></div>
          <Provider name="Newshosting" health="98.7%" speed="38.6 MB/s" />
          <Provider name="Eweka" health="95.3%" speed="32.1 MB/s" />
          <Provider name="Astraweb" health="94.2%" speed="28.7 MB/s" />
          <Provider name="Usenet.Farm" health="90.1%" speed="24.3 MB/s" warning />
        </Panel>

        <Panel title="Recent Activity" action="Activity">
          <Activity text="Imported: Project Hail Mary" time="2m ago" />
          <Activity text="Downloaded: The Will of the Many" time="8m ago" />
          <Activity text="Release found for wanted book" time="12m ago" />
          <Activity text="Indexer started deep inspection" time="15m ago" />
          <Activity text="Backfill progressed: 1,247 / 3,000 days" time="22m ago" />
        </Panel>
      </div>
    </section>
  )
}

function Metric({ icon, label, value, sub, note, good, warn }: { icon:string; label:string; value:string; sub:string; note:string; good?:boolean; warn?:boolean }) {
  return <div className="metric"><span className="metric-icon">{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{sub}</p><em className={good ? 'green' : warn ? 'orange' : ''}>{note}</em></div></div>
}
function Panel({ title, action, children }: { title:string; action:string; children:React.ReactNode }) { return <section className="panel"><div className="panel-title"><h3>{title}</h3><span className="panel-action">{action}</span></div>{children}</section> }
function ReleaseRow({ title, byline, format, size, index }: { title:string; byline:string; format:string; size:string; index:number }) { return <div className="release"><span className={`cover c${index}`}>Lx</span><div><b>{title}</b><p>{byline}</p><small>{format}</small><small>{size}</small><small className="complete">100%</small></div><time>{index * 7 + 2}m ago</time></div> }
function Download({ title, pct, speed, meta }: { title:string; pct:number; speed:string; meta:string }) { return <div className="download"><b>{title}</b><div className="download-line"><div className="progress"><i style={{width:`${pct}%`}} /></div><span>{pct}%</span><button aria-label={`Pause ${title}`}>Ⅱ</button></div><p>{speed} · {meta}</p></div> }
function Wanted({ title, author, status, warning, danger }: { title:string; author:string; status:string; warning?:boolean; danger?:boolean }) { return <div className="wanted"><span className="tiny-cover">Lx</span><div><b>{title}</b><p>{author}</p></div><em className={danger ? 'danger' : warning ? 'warning' : 'success'}>{status}</em></div> }
function Stat({ label, value, good }: { label:string; value:string; good?:boolean }) { return <div className="stat"><span>{label}</span><b className={good ? 'ok' : ''}>{value}</b></div> }
function Provider({ name, health, speed, warning }: { name:string; health:string; speed:string; warning?:boolean }) { return <div className="provider"><span>{name}</span><b>{health}</b><span>{speed}</span><em className={warning ? 'warning' : 'success'}>{warning ? 'Warm' : 'Healthy'}</em></div> }
function Activity({ text, time }: { text:string; time:string }) { return <div className="activity"><span>◎</span><p>{text}</p><time>{time}</time></div> }
