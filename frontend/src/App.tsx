import { useEffect, useState } from 'react'

type Health = { status: string; app: string }
type Book = { id: string; title: string; author: string; narrator?: string | null; format: string; path: string; size: number }

const nav = ['Home', 'Wanted', 'Downloads', 'Library', 'Authors', 'Series', 'Narrators', 'Indexer', 'Activity', 'Settings']

const recent = [
  ['Project Hail Mary', 'Andy Weir · Ray Porter', 'M4B', '1.20 GB'],
  ['The Will of the Many', 'James Islington · Euan Morton', 'M4B', '1.15 GB'],
  ['Dungeon Crawler Carl Book 6', 'Matt Dinniman · Jeff Hays', 'MP3', '980 MB'],
  ['Fourth Wing', 'Rebecca Yarros · Rebecca Soler', 'M4B', '1.05 GB'],
]

function Logo() {
  return (
    <div className="logo" aria-label="LoreX">
      <span className="logo-mark"><span className="book">⌄</span><span className="phones">∩</span></span>
      <span className="logo-text">Lore<span>X</span></span>
    </div>
  )
}

function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [books, setBooks] = useState<Book[]>([])

  useEffect(() => {
    fetch('/api/health').then((r) => r.ok ? r.json() : null).then(setHealth).catch(() => setHealth(null))
    fetch('/api/library/books').then((r) => r.ok ? r.json() : null).then((data) => setBooks(data?.books ?? [])).catch(() => setBooks([]))
  }, [])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        <nav>
          {nav.map((item, index) => <button key={item} className={index === 0 ? 'active' : ''}><span className="nav-dot">{index === 0 ? '⌂' : '·'}</span>{item}{item === 'Wanted' && <em>17</em>}{item === 'Downloads' && <em>3</em>}</button>)}
        </nav>
        <div className="system">
          <h4>System</h4>
          <p><span>Indexer</span><b className="ok">● Running</b></p>
          <p><span>Downloads</span><b>● 3 Active</b></p>
          <p><span>Backfill</span><b>1,247 days</b></p>
          <div className="mini-progress"><i /></div>
          <p><span>Newshosting</span><b className="ok">98.7%</b></p>
          <p><span>Eweka</span><b className="ok">95.3%</b></p>
        </div>
        <div className="sidebar-foot">Light <span>v0.1.0</span></div>
      </aside>

      <main>
        <header>
          <button className="menu">☰</button>
          <div className="search">Search books, authors, series, or narrators… <span>⌕</span></div>
          <div className="header-right">⌁ Activity <span className="bell">♧<i>3</i></span><span className="avatar">TU</span></div>
        </header>

        <section className="content">
          <div className="metrics">
            <Metric icon="▣" label="Library" value={books.length ? books.length.toLocaleString() : '2,481'} sub="books" note="+24 this week" />
            <Metric icon="▱" label="Wanted" value="17" sub="books" note="3 found today" warn />
            <Metric icon="⇩" label="Downloading" value="3" sub="active" note="2.34 TB remaining" />
            <Metric icon="◉" label="Indexed" value="184,271" sub="audiobooks" note="+1,293 today" good />
            <Metric icon="◷" label="Uptime" value="6d 14h" sub="system uptime" note={health?.status === 'ok' ? 'API healthy' : 'UI preview'} good />
          </div>

          <div className="dashboard-grid">
            <Panel title="Recent Releases" action="View All">
              <div className="release-list">{recent.map(([title, byline, format, size], i) => <ReleaseRow key={title} title={title} byline={byline} format={format} size={size} index={i} />)}</div>
            </Panel>

            <Panel title="Active Downloads" action="View All">
              <Download title="Project Hail Mary" pct={68} speed="34.2 MB/s" meta="812 MB / 1.20 GB · 03:41 ETA" />
              <Download title="The Will of the Many" pct={42} speed="28.7 MB/s" meta="486 MB / 1.15 GB · 04:02 ETA" />
              <Download title="The Martian" pct={12} speed="22.1 MB/s" meta="108 MB / 900 MB · 00:36 ETA" />
            </Panel>

            <Panel title="Wanted Matches" action="View All">
              <Wanted title="Mistborn: The Hero of Ages" author="Brandon Sanderson" status="Release Found" />
              <Wanted title="Cradle: Wintersteel" author="Will Wight" status="Release Found" />
              <Wanted title="The Stormlight Archive #5" author="Brandon Sanderson" status="Searching" warning />
              <Wanted title="Red Rising: Iron Gold" author="Pierce Brown" status="Missing" danger />
              <Wanted title="The Name of the Wind" author="Patrick Rothfuss" status="Missing" danger />
            </Panel>

            <Panel title="Indexer Status" action="View Indexer">
              <Stat label="Status" value="Running" good />
              <Stat label="Current Group" value="alt.binaries.audio.audiobook" />
              <Stat label="Article" value="231,481,902" />
              <Stat label="Headers/sec" value="18,430" />
              <Stat label="Candidates" value="418" />
              <Stat label="Audiobooks" value="31" />
              <Stat label="Rejected Articles" value="299" />
            </Panel>

            <Panel title="Provider Health" action="View All">
              <div className="provider-head"><span>Provider</span><span>Health</span><span>Speed</span><span>Status</span></div>
              <Provider name="Newshosting" health="98.7%" speed="38.6 MB/s" />
              <Provider name="Eweka" health="95.3%" speed="32.1 MB/s" />
              <Provider name="Astraweb" health="94.2%" speed="28.7 MB/s" />
              <Provider name="Usenet.Farm" health="90.1%" speed="24.3 MB/s" warning />
            </Panel>

            <Panel title="Recent Activity" action="View All">
              <Activity text="Imported: Project Hail Mary" time="2m ago" />
              <Activity text="Downloaded: The Will of the Many" time="8m ago" />
              <Activity text="Release found for wanted book" time="12m ago" />
              <Activity text="Indexer started deep inspection" time="15m ago" />
              <Activity text="Backfill progressed: 1,247 / 3,000 days" time="22m ago" />
            </Panel>
          </div>
        </section>
      </main>
    </div>
  )
}

function Metric({ icon, label, value, sub, note, good, warn }: { icon:string; label:string; value:string; sub:string; note:string; good?:boolean; warn?:boolean }) {
  return <div className="metric"><span className="metric-icon">{icon}</span><div><small>{label}</small><strong>{value}</strong><p>{sub}</p><em className={good ? 'green' : warn ? 'orange' : ''}>{note}</em></div></div>
}
function Panel({ title, action, children }: { title:string; action:string; children:React.ReactNode }) { return <section className="panel"><div className="panel-title"><h3>{title}</h3><a>{action}</a></div>{children}</section> }
function ReleaseRow({ title, byline, format, size, index }: { title:string; byline:string; format:string; size:string; index:number }) { return <div className="release"><span className={`cover c${index}`}>Lx</span><div><b>{title}</b><p>{byline}</p><small>{format}</small><small>{size}</small><small className="complete">100%</small></div><time>{index * 7 + 2}m ago</time></div> }
function Download({ title, pct, speed, meta }: { title:string; pct:number; speed:string; meta:string }) { return <div className="download"><b>{title}</b><div className="download-line"><div className="progress"><i style={{width:`${pct}%`}} /></div><span>{pct}%</span><button>Ⅱ</button></div><p>{speed} · {meta}</p></div> }
function Wanted({ title, author, status, warning, danger }: { title:string; author:string; status:string; warning?:boolean; danger?:boolean }) { return <div className="wanted"><span className="tiny-cover">Lx</span><div><b>{title}</b><p>{author}</p></div><em className={danger ? 'danger' : warning ? 'warning' : 'success'}>{status}</em></div> }
function Stat({ label, value, good }: { label:string; value:string; good?:boolean }) { return <div className="stat"><span>{label}</span><b className={good ? 'ok' : ''}>{value}</b></div> }
function Provider({ name, health, speed, warning }: { name:string; health:string; speed:string; warning?:boolean }) { return <div className="provider"><span>{name}</span><b>{health}</b><span>{speed}</span><em className={warning ? 'warning' : 'success'}>{warning ? 'Warm' : 'Healthy'}</em></div> }
function Activity({ text, time }: { text:string; time:string }) { return <div className="activity"><span>◎</span><p>{text}</p><time>{time}</time></div> }

export default App
