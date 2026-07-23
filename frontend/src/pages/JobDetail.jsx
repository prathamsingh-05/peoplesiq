import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, downloadFile } from '../api.js'
import { Alert, Badge, GuidanceChip, Score, Spinner, fmtDate, useAsync } from '../components.jsx'

export default function JobDetail() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [tab, setTab] = useState('scorecard')
  const [deleteError, setDeleteError] = useState('')
  const job = useAsync(() => api.get(`/api/jobs/${jobId}`), [jobId])

  if (job.loading) return <Spinner />
  if (job.error) return <Alert kind="error">{job.error}</Alert>
  const data = job.data

  const deleteJob = async () => {
    if (!window.confirm(
      `Delete "${data.title}" (${data.job_code})? This permanently removes the job, its ` +
      `scorecard, and all ${data.candidate_count} candidate(s) and evaluations for it. This cannot be undone.`
    )) return
    setDeleteError('')
    try {
      await api.del(`/api/jobs/${jobId}`)
      navigate('/jobs')
    } catch (e) { setDeleteError(e.message); alert(e.message) }
  }

  return (
    <div>
      <p className="small"><Link to="/jobs">← All jobs</Link></p>
      <div className="row between">
        <div>
          <h1>{data.title} <span className="muted small">({data.job_code})</span></h1>
          <p className="sub">
            {data.client_name} · {data.location || 'location TBD'} · {data.work_model || '—'} ·
            {' '}{data.working_hours || 'hours TBD'} · <Badge value={data.status} />
            {data.seniority_tier && <> · <Badge value={data.seniority_tier} /></>}
            {data.compensation_range && <> · {data.compensation_range}</>}
          </p>
          {data.good_enough_note && (
            <p className="small muted">Calibration: {data.good_enough_note}</p>
          )}
          {data.ideal_candidate_profile && (
            <p className="small muted">Strong-fit example: {data.ideal_candidate_profile}</p>
          )}
          {data.domain_context && (
            <p className="small muted">Domain weighting: {data.domain_context}</p>
          )}
        </div>
        <div className="row">
          <button className="btn secondary"
                  onClick={() => downloadFile(`/api/jobs/${jobId}/export/leaderboard`, 'leaderboard.xlsx')}>
            Export leaderboard
          </button>
          <button className="btn secondary"
                  onClick={() => downloadFile(`/api/jobs/${jobId}/export/hm-summaries`, 'summaries.xlsx')
                    .catch((e) => alert(e.message))}>
            Export HM summaries
          </button>
          <button className="btn danger" onClick={deleteJob}>Delete job</button>
        </div>
      </div>
      {deleteError && <Alert kind="error" onClose={() => setDeleteError('')}>{deleteError}</Alert>}

      <div className="tabs">
        {['scorecard', 'upload', 'leaderboard', 'rediscover'].map((t) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {{ scorecard: '1 · Scorecard', upload: '2 · Upload CVs',
               leaderboard: '3 · Screen & Leaderboard', rediscover: '4 · Rediscover talent' }[t]}
          </button>
        ))}
      </div>

      {tab === 'scorecard' && <ScorecardTab jobId={jobId} onApproved={job.reload} />}
      {tab === 'upload' && <UploadTab jobId={jobId} hasScorecard={data.has_approved_scorecard} />}
      {tab === 'leaderboard' && <LeaderboardTab jobId={jobId} hasScorecard={data.has_approved_scorecard} />}
      {tab === 'rediscover' && <RediscoverTab jobId={jobId} hasScorecard={data.has_approved_scorecard} />}
    </div>
  )
}

// ---------------------------------------------------------------------------
function ScorecardTab({ jobId, onApproved }) {
  const [scorecard, setScorecard] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [rows, setRows] = useState([])

  const load = () => api.get(`/api/jobs/${jobId}/scorecard`)
    .then((s) => { setScorecard(s); setRows(s.criteria) })
    .catch(() => setScorecard(null))
  useEffect(() => { load() }, [jobId])

  const generate = async () => {
    setBusy(true); setError('')
    try {
      const s = await api.post(`/api/jobs/${jobId}/scorecard/generate`)
      setScorecard(s); setRows(s.criteria)
      setMessage(`Scorecard v${s.version} generated ${s.generated_by_ai ? 'by AI' : 'from job fields (offline mode)'} — review, edit, then approve.`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const saveEdits = async () => {
    setBusy(true); setError('')
    try {
      const s = await api.put(`/api/jobs/${jobId}/scorecard/${scorecard.id}`, {
        criteria: rows.map(({ category, name, description, weight, is_mandatory }) =>
          ({ category, name, description, weight: Number(weight), is_mandatory })),
      })
      setScorecard(s); setRows(s.criteria); setEditing(false)
      setMessage('Edits saved. Approve when ready.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const approve = async () => {
    if (!window.confirm('Approve this scorecard? It becomes the immutable basis for all screening of this job.')) return
    setBusy(true); setError('')
    try {
      const s = await api.post(`/api/jobs/${jobId}/scorecard/${scorecard.id}/approve`)
      setScorecard(s); setMessage('Scorecard approved — screening is now unlocked.')
      onApproved()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const setRow = (i, key) => (e) => {
    const next = [...rows]
    next[i] = { ...next[i], [key]: key === 'is_mandatory' ? e.target.checked : e.target.value }
    setRows(next)
  }

  return (
    <div className="card">
      <div className="row between">
        <h2>Evaluation scorecard {scorecard && <Badge value={scorecard.status} />}</h2>
        <div className="row">
          {scorecard && scorecard.status === 'draft' && !editing &&
            <button className="btn secondary" onClick={() => setEditing(true)}>Edit criteria</button>}
          {editing && <button className="btn ok" onClick={saveEdits} disabled={busy}>Save edits</button>}
          {scorecard && scorecard.status === 'draft' &&
            <button className="btn" onClick={approve} disabled={busy}>Approve scorecard ✓</button>}
          <button className="btn secondary" onClick={generate} disabled={busy}>
            {scorecard ? 'Regenerate (new version)' : busy ? 'Generating…' : 'Generate from JD'}
          </button>
        </div>
      </div>
      <Alert kind="success" onClose={() => setMessage('')}>{message}</Alert>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>

      {!scorecard && <p className="muted">No scorecard yet. Generate one from the job description —
        the AI converts the JD into weighted, verifiable criteria which you must review and approve
        before any resume can be screened.</p>}

      {scorecard && (
        <table className="data">
          <thead><tr>
            <th>Category</th><th>Criterion</th><th>What counts as evidence</th>
            <th>Weight</th><th>Mandatory</th>
          </tr></thead>
          <tbody>
            {rows.map((c, i) => (
              <tr key={i}>
                <td>{editing ? (
                  <select value={c.category} onChange={setRow(i, 'category')}>
                    {['mandatory', 'experience', 'technical_skills', 'domain', 'qualifications',
                      'seniority', 'location_hours', 'stability', 'preferred'].map((x) =>
                        <option key={x} value={x}>{x}</option>)}
                  </select>) : <Badge value={c.category} />}</td>
                <td>{editing ? <input value={c.name} onChange={setRow(i, 'name')} /> : <b>{c.name}</b>}</td>
                <td>{editing ? <textarea rows={2} value={c.description} onChange={setRow(i, 'description')} />
                  : <span className="muted">{c.description}</span>}</td>
                <td>{editing ? <input type="number" step="0.25" min="0.25" max="5" style={{ width: 70 }}
                                      value={c.weight} onChange={setRow(i, 'weight')} /> : c.weight}</td>
                <td>{editing ? <input type="checkbox" checked={c.is_mandatory} onChange={setRow(i, 'is_mandatory')} />
                  : (c.is_mandatory ? '✓' : '—')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {scorecard?.approved_at && (
        <p className="small muted">Approved by {scorecard.approved_by} on {fmtDate(scorecard.approved_at)}.</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
function UploadTab({ jobId, hasScorecard }) {
  const fileRef = useRef()
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const log = useAsync(() => api.get(`/api/jobs/${jobId}/processing-log`), [jobId])

  const upload = async () => {
    const files = fileRef.current.files
    if (!files.length) { setError('Choose one or more PDF/DOCX resumes first'); return }
    setBusy(true); setError('')
    const formData = new FormData()
    for (const f of files) formData.append('files', f)
    try {
      const r = await api.postForm(`/api/jobs/${jobId}/candidates/upload`, formData)
      setResult(r); log.reload(); fileRef.current.value = ''
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="card">
        <h2>Upload resumes (PDF / DOCX)</h2>
        {!hasScorecard && <Alert kind="info">You can upload now, but screening stays locked until
          the scorecard is approved.</Alert>}
        <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
        <div className="row">
          <input type="file" ref={fileRef} multiple accept=".pdf,.docx,.doc,.txt" style={{ flex: 1 }} />
          <button className="btn" onClick={upload} disabled={busy}>
            {busy ? 'Uploading & parsing…' : 'Upload batch'}
          </button>
        </div>
        {result && (
          <Alert kind="success" onClose={() => setResult(null)}>
            Batch done — processed {result.processed}, duplicates {result.duplicates},
            unreadable {result.unreadable}, errors {result.errors}.
          </Alert>
        )}
      </div>

      <div className="card">
        <h2>Processing log</h2>
        {log.loading ? <Spinner /> : (
          <table className="data">
            <thead><tr><th>Time</th><th>File</th><th>Status</th><th>Detail</th></tr></thead>
            <tbody>
              {log.data.map((row) => (
                <tr key={row.id}>
                  <td className="small">{fmtDate(row.created_at)}</td>
                  <td>{row.candidate_id
                    ? <Link to={`/candidates/${row.candidate_id}`}>{row.filename}</Link>
                    : row.filename}</td>
                  <td><Badge value={row.status} /></td>
                  <td className="small muted">{row.message}</td>
                </tr>
              ))}
              {log.data.length === 0 && <tr><td colSpan={4} className="muted">Nothing processed yet.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function _poolInsightTone(headline) {
  const h = (headline || '').toLowerCase()
  if (h.includes('strong')) return 'success'
  if (h.includes('weak') || h.includes('missing the same')) return 'warn'
  return 'info'
}

// ---------------------------------------------------------------------------
function LeaderboardTab({ jobId, hasScorecard }) {
  const board = useAsync(() => api.get(`/api/jobs/${jobId}/leaderboard`), [jobId])
  const insight = useAsync(() => api.get(`/api/jobs/${jobId}/pool-insight`), [jobId])
  const [progress, setProgress] = useState(null)
  const [error, setError] = useState('')
  const timer = useRef()

  const poll = () => {
    api.get(`/api/jobs/${jobId}/screen/status`).then((s) => {
      setProgress(s)
      if (s.running) timer.current = setTimeout(poll, 2000)
      else { board.reload(); insight.reload() }
    })
  }
  useEffect(() => () => clearTimeout(timer.current), [])

  const screen = async () => {
    setError('')
    try {
      await api.post(`/api/jobs/${jobId}/screen`)
      poll()
    } catch (e) { setError(e.message) }
  }

  const rescreenAll = async () => {
    if (!window.confirm(
      'Re-run every candidate on this job against the current scorecard? Use this after ' +
      'editing scorecard weights or criteria so the whole leaderboard reflects the update.'
    )) return
    setError('')
    try {
      await api.post(`/api/jobs/${jobId}/rescreen-all`)
      poll()
    } catch (e) { setError(e.message) }
  }

  const [selected, setSelected] = useState(new Set())
  const toggle = (id) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }
  const bulkDecide = async (decision) => {
    let reason = ''
    if (decision === 'reject') {
      reason = window.prompt(`Rejection reason for ${selected.size} candidate(s) (mandatory):`)
      if (!reason) return
    }
    try {
      await api.post(`/api/jobs/${jobId}/decisions/bulk`,
        { candidate_ids: [...selected], decision, rejection_reason: reason })
      setSelected(new Set()); board.reload()
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="card">
      <div className="row between">
        <h2>Candidate leaderboard</h2>
        <div className="row">
          <button className="btn secondary" onClick={rescreenAll}
                  disabled={!hasScorecard || progress?.running || board.data?.length === 0}
                  title="Re-run everyone against the current scorecard — use after editing weights or criteria">
            ↻ Rescreen all candidates
          </button>
          <button className="btn" onClick={screen} disabled={!hasScorecard || progress?.running}>
            {progress?.running ? 'Screening…' : '▶ Screen all pending resumes'}
          </button>
        </div>
      </div>
      {!hasScorecard && <Alert kind="info">Approve the scorecard first (tab 1).</Alert>}
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      {insight.data && insight.data.pool_size > 0 && (
        <Alert kind={_poolInsightTone(insight.data.headline)}>
          <b>{insight.data.headline}.</b> {insight.data.note}
        </Alert>
      )}
      {progress?.running && (
        <div style={{ marginBottom: 12 }}>
          <div className="progressbar">
            <div style={{ width: `${(100 * (progress.done + progress.failed)) / progress.total}%` }} />
          </div>
          <span className="small muted">{progress.done}/{progress.total} screened
            {progress.failed > 0 && `, ${progress.failed} failed`}</span>
        </div>
      )}
      {selected.size > 0 && (
        <div className="row" style={{ marginBottom: 10 }}>
          <span className="small"><b>{selected.size}</b> selected —</span>
          <button className="btn sm ok" onClick={() => bulkDecide('shortlist')}>Shortlist</button>
          <button className="btn sm secondary" onClick={() => bulkDecide('hold')}>Hold</button>
          <button className="btn sm danger" onClick={() => bulkDecide('reject')}>Reject…</button>
          <button className="btn sm secondary" onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}

      {board.loading ? <Spinner /> : (
        <table className="data">
          <thead><tr>
            <th></th><th>#</th><th>Candidate</th><th>Guidance</th><th>Match</th><th>Mandatory</th><th>Rel. exp</th>
            <th>Key strengths</th><th>Gaps</th><th>Risk flags</th>
            <th>AI recommendation</th><th>Confidence</th><th>Recruiter decision</th>
          </tr></thead>
          <tbody>
            {board.data.map((row) => (
              <tr key={row.candidate_id}>
                <td><input type="checkbox" style={{ width: 'auto' }}
                           checked={selected.has(row.candidate_id)}
                           onChange={() => toggle(row.candidate_id)} /></td>
                <td><b>{row.rank}</b></td>
                <td>
                  <Link to={`/candidates/${row.candidate_id}`}><b>{row.candidate}</b></Link>
                  <div className="small muted">{row.candidate_code}</div>
                  {row.flagged_for_review && <Badge value="pending_review" />}
                </td>
                <td><GuidanceChip guidance={row.recruiter_guidance} /></td>
                <td><Score value={row.overall_match} /></td>
                <td><Badge value={row.mandatory_criteria} /></td>
                <td>{row.relevant_experience_years} y</td>
                <td className="small">{row.key_strengths.slice(0, 3).join('; ') || '—'}</td>
                <td className="small">{row.gaps.slice(0, 3).join('; ') || '—'}</td>
                <td className="small">{row.risk_flags.slice(0, 2).join('; ') || '—'}</td>
                <td><Badge value={row.recommendation} /></td>
                <td><Badge value={row.confidence} /></td>
                <td><Badge value={row.recruiter_decision || row.status} /></td>
              </tr>
            ))}
            {board.data.length === 0 && (
              <tr><td colSpan={13} className="muted">No screened candidates yet — upload resumes and run screening.</td></tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
function RediscoverTab({ jobId, hasScorecard }) {
  const [matches, setMatches] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [error, setError] = useState(''); const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  const load = () => {
    setLoading(true); setError('')
    api.get(`/api/jobs/${jobId}/rediscover`)
      .then(setMatches).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }
  const toggle = (id) => {
    const next = new Set(selected); next.has(id) ? next.delete(id) : next.add(id); setSelected(next)
  }
  const pull = () => api.post(`/api/jobs/${jobId}/rediscover/pull`, { candidate_ids: [...selected] })
    .then((r) => { setMessage(`Pulled ${r.pulled.length} candidate(s) in — run screening on the leaderboard tab to evaluate them.`); setSelected(new Set()); load() })
    .catch((e) => setError(e.message))

  return (
    <div className="card">
      <div className="row between">
        <div>
          <h2>Rediscover talent</h2>
          <p className="small muted">Resurface strong candidates already in the system from other
            roles — including <b>silver medalists</b> who reached interview/offer stages elsewhere.
            This is the difference between a 12-day and a 42-day time-to-fill.</p>
        </div>
        <button className="btn" onClick={load} disabled={!hasScorecard || loading}>
          {loading ? 'Searching…' : '🔎 Search the candidate base'}
        </button>
      </div>
      {!hasScorecard && <Alert kind="info">Approve this job's scorecard first (tab 1).</Alert>}
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      <Alert kind="success" onClose={() => setMessage('')}>{message}</Alert>

      {selected.size > 0 &&
        <button className="btn ok" style={{ marginBottom: 10 }} onClick={pull}>
          Pull {selected.size} candidate(s) into this job →
        </button>}

      {matches && (
        <table className="data">
          <thead><tr>
            <th></th><th>Candidate</th><th>Match</th><th>From role</th><th>Prior outcome</th><th>Matched on</th>
          </tr></thead>
          <tbody>
            {matches.map((m) => (
              <tr key={m.candidate_id}>
                <td><input type="checkbox" style={{ width: 'auto' }}
                           checked={selected.has(m.candidate_id)}
                           onChange={() => toggle(m.candidate_id)} /></td>
                <td>
                  <Link to={`/candidates/${m.candidate_id}`}><b>{m.full_name}</b></Link>
                  <div className="small muted">{m.candidate_code}
                    {m.current_role && ` · ${m.current_role}`}</div>
                  {m.silver_medalist && <span className="badge ok">🥈 silver medalist</span>}
                </td>
                <td><Score value={m.match_score} /></td>
                <td className="small">{m.source_job_code}<br /><span className="muted">{m.source_job_title}</span></td>
                <td className="small"><Badge value={m.prior_status} />
                  {m.prior_recruiter_decision && <> · <Badge value={m.prior_recruiter_decision} /></>}</td>
                <td className="small muted">{m.match_terms.join(', ')}</td>
              </tr>
            ))}
            {matches.length === 0 &&
              <tr><td colSpan={6} className="muted">No matching prior candidates found.</td></tr>}
          </tbody>
        </table>
      )}
      {!matches && !loading &&
        <p className="muted">Click “Search the candidate base” to find prior candidates who fit this role.</p>}
    </div>
  )
}
