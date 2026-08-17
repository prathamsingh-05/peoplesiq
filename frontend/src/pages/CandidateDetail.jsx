import React, { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Badge, Score, Spinner, fmtDate, fmtDay, useAsync } from '../components.jsx'

export default function CandidateDetail() {
  const { candidateId } = useParams()
  const [tab, setTab] = useState('assessment')
  const candidate = useAsync(() => api.get(`/api/candidates/${candidateId}`), [candidateId])
  const history = useAsync(() => api.get(`/api/candidates/${candidateId}/history`), [candidateId])

  if (candidate.loading) return <Spinner />
  if (candidate.error) return <Alert kind="error">{candidate.error}</Alert>
  const c = candidate.data

  return (
    <div>
      <p className="small"><Link to={`/jobs/${c.job_id}`}>← Back to job</Link></p>
      <div className="row between">
        <div>
          <h1>{c.full_name || c.resume_filename} <span className="muted small">({c.candidate_code})</span></h1>
          <p className="sub">
            {c.current_role && `${c.current_role} @ ${c.current_employer} · `}
            {c.email || 'no email'} · {c.phone || 'no phone'} · {c.location || 'location unknown'}
            {' '}· <Badge value={c.status} />
            {c.flagged_for_review && <> · <Badge value="pending_review" /> fairness audit</>}
          </p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <Score value={c.ai_score} />
          <div className="small muted">AI score · <Badge value={c.ai_recommendation} /></div>
        </div>
      </div>

      {history.data?.length > 0 && (
        <Alert kind="info">
          <b>Also applied before:</b>{' '}
          {history.data.map((h, i) => (
            <span key={h.candidate_id}>
              {i > 0 && ' · '}
              <Link to={`/jobs/${h.job_id}`}>{h.job_title || h.job_code}</Link>
              {' '}(<Badge value={h.status} />
              {h.overall_score != null && <>, scored {Math.round(h.overall_score)}</>})
            </span>
          ))}
        </Alert>
      )}

      <div className="tabs">
        {[['assessment', 'Assessment'], ['questions', 'Screening questions'],
          ['call', 'Call & decision'], ['summary', 'HM summary'],
          ['emails', 'Emails'], ['engagement', 'Keep-warm'],
          ['interviews', 'Interviews'], ['record', 'Record & corrections']].map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === 'assessment' && <AssessmentTab candidateId={candidateId} candidate={c} />}
      {tab === 'questions' && <QuestionsTab candidateId={candidateId} />}
      {tab === 'call' && <CallDecisionTab candidate={c} reload={candidate.reload} />}
      {tab === 'summary' && <SummaryTab candidateId={candidateId} />}
      {tab === 'emails' && <EmailsTab candidate={c} />}
      {tab === 'engagement' && <EngagementTab candidate={c} reload={candidate.reload} />}
      {tab === 'interviews' && <InterviewsTab candidateId={candidateId} />}
      {tab === 'record' && <RecordTab candidate={c} reload={candidate.reload} />}
    </div>
  )
}

// ---------------------------------------------------------------------------
function CareerTimelineCard({ timeline }) {
  if (!timeline?.entries?.length) return null
  return (
    <div className="card">
      <h2>Career timeline <span className="small muted">(computed from dated work history, not AI-estimated)</span></h2>
      <ul className="clean">
        {timeline.entries.map((e, i) => (
          <li key={i}>
            <b>{e.role || 'Role not specified'}</b> @ {e.employer || 'employer not specified'}
            {' — '}{e.start_label} to {e.end_label} ({e.duration_months} mo{e.ongoing ? ', current' : ''})
          </li>
        ))}
      </ul>
      <p className="small muted">
        ~{timeline.total_experience_years} years total across {timeline.employer_count} role(s)
        {timeline.short_stint_count > 0 && <>, {timeline.short_stint_count} stint(s) under a year</>}.
      </p>
      {timeline.gaps?.length > 0 && (
        <p className="small muted">
          <b>Gaps:</b> {timeline.gaps.map((g, i) => `${g.months} mo (${g.from}–${g.to})`).join(' · ')}
        </p>
      )}
    </div>
  )
}

function DimensionsCard({ ev }) {
  if (!ev.score_dimensions?.length) return null
  const tone = (d) => {
    if (d.evidence_coverage_pct < 50) return 'unknown'
    if (d.score >= 70) return 'good'
    if (d.score >= 45) return 'mid'
    return 'weak'
  }
  return (
    <div className="card">
      <div className="row between">
        <h2>Where they're strong, weak, and unknown</h2>
        {ev.role_family && <span className="small muted">read as: {ev.role_family}</span>}
      </div>
      {ev.dimension_headline && <p>{ev.dimension_headline}</p>}
      <table className="data">
        <thead><tr>
          <th>Dimension</th><th>Score</th><th>Evidence coverage</th><th>Confirmed</th><th>Not established</th>
        </tr></thead>
        <tbody>
          {ev.score_dimensions.map((d) => (
            <tr key={d.key}>
              <td><b>{d.label}</b>{!d.scored && <span className="small muted"> (bonus only)</span>}</td>
              <td><span className={`dim-score ${tone(d)}`}>{Math.round(d.score)}</span></td>
              <td>
                <div className="progressbar sm"><div style={{ width: `${d.evidence_coverage_pct}%` }} /></div>
                <span className="small muted">{d.evidence_coverage_pct}% of {d.criterion_count}</span>
              </td>
              <td className="small">{d.confirmed?.join(', ') || <span className="muted">—</span>}</td>
              <td className="small muted">{d.unknown?.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">Low evidence coverage means the resume didn't say — that's a
        question for the call, not a weakness. A low score with high coverage is a real gap.</p>
      {ev.scope_assessment?.note && (
        <>
          <h3>Level actually demonstrated (not job titles)</h3>
          <p className="small muted">{ev.scope_assessment.note}</p>
        </>
      )}
    </div>
  )
}

function AssessmentTab({ candidateId, candidate }) {
  const evaluation = useAsync(
    () => api.get(`/api/candidates/${candidateId}/evaluation`).catch((e) => {
      if (e.status === 404) return null
      throw e
    }), [candidateId])

  if (evaluation.loading) return <Spinner />
  const ev = evaluation.data

  const list = (items) => items?.length
    ? <ul className="clean">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
    : <span className="muted">None identified</span>

  if (!ev) return (
    <div>
      <CareerTimelineCard timeline={candidate?.career_timeline} />
      <Alert kind="info">Not screened yet — run screening from the job's leaderboard tab.</Alert>
    </div>
  )

  const g = ev.recruiter_guidance

  return (
    <div>
      <DimensionsCard ev={ev} />
      <CareerTimelineCard timeline={candidate?.career_timeline} />
      {g && (
        <div className={`guidance-banner ${g.tone}`}>
          <h2>{g.headline}</h2>
          <p>{g.reason_in_plain_english}</p>
          {g.top_strengths?.length > 0 && (
            <p><b>What stands out:</b> {g.top_strengths.join(' · ')}</p>
          )}
          {g.things_to_check_on_the_call?.length > 0 && (
            <p><b>Check on the call:</b> {g.things_to_check_on_the_call.join(' · ')}</p>
          )}
          {g.closing_the_gap?.length > 0 && (
            <p><b>Closing the gap ({g.points_to_shortlist} pts to shortlist):</b>{' '}
              {g.closing_the_gap.map((c) => `${c.criterion} (+${c.points})`).join(' · ')}</p>
          )}
          {g.level_context && <p className="small">{g.level_context}</p>}
          <p className="next-step">Next step: {g.next_step}</p>
        </div>
      )}

      <div className="card">
        <div className="row between">
          <h2>Executive summary</h2>
          <span className="small muted">
            engine: {ev.engine}{ev.model_used && ` (${ev.model_used})`} · confidence <Badge value={ev.confidence} />
            · mandatory <Badge value={ev.mandatory_status} />
            {ev.overall_impression && <> · whole-person read <Badge value={ev.overall_impression} /></>}
          </span>
        </div>
        <p>{ev.executive_summary}</p>
        {ev.overall_impression_note && (
          <>
            <h3>Who this person is, as a professional</h3>
            <p className="small muted">{ev.overall_impression_note}</p>
          </>
        )}
        <h3>Why this recommendation</h3>
        <p>{ev.explanation}</p>
        {ev.calibration_notes && (
          <>
            <h3>How this was judged for this role</h3>
            <p className="small muted">{ev.calibration_notes}</p>
          </>
        )}
      </div>

      <div className="grid cols-2">
        <div className="card"><h3>Key strengths</h3>{list(ev.key_strengths)}</div>
        <div className="card"><h3>Gaps (vs scorecard)</h3>{list(ev.gaps)}</div>
        <div className="card"><h3>Risk flags</h3>{list(ev.risk_flags)}</div>
        <div className="card"><h3>Relevant projects / achievements</h3>{list(ev.relevant_projects)}</div>
        <div className="card"><h3>Missing information</h3>{list(ev.missing_information)}</div>
        <div className="card"><h3>Possible inconsistencies</h3>{list(ev.inconsistencies)}</div>
      </div>

      <div className="card">
        <h2>Evidence per criterion</h2>
        <p className="small muted">Every status is tied to a verbatim quote from the resume;
          quotes that could not be verified against the source text were automatically downgraded.</p>
        <table className="data">
          <thead><tr><th>Criterion</th><th>Category</th><th>Status</th><th>Evidence from resume</th><th>Notes</th></tr></thead>
          <tbody>
            {ev.criterion_results.map((r) => (
              <tr key={r.criterion_id}>
                <td><b>{r.name}</b>{r.is_mandatory && <span className="badge bad" style={{ marginLeft: 6 }}>mandatory</span>}</td>
                <td><Badge value={r.category} /></td>
                <td><Badge value={r.status} />{r.evidence_verified && <span title="Quote verified in resume"> ✓</span>}</td>
                <td>{r.evidence ? <div className="evidence-quote">“{r.evidence}”</div> : <span className="muted">—</span>}</td>
                <td className="small muted">{r.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
function QuestionsTab({ candidateId }) {
  const questions = useAsync(() => api.get(`/api/candidates/${candidateId}/questions`), [candidateId])
  const [error, setError] = useState('')

  const regenerate = () => api.post(`/api/candidates/${candidateId}/questions/regenerate`)
    .then(() => questions.reload()).catch((e) => setError(e.message))
  const saveAnswer = (id, answer) => api.patch(`/api/questions/${id}/answer`, { answer })
    .catch((e) => setError(e.message))

  if (questions.loading) return <Spinner />
  const groups = { eligibility: [], skill_evidence: [], gap_probing: [], motivation: [] }
  for (const q of questions.data) (groups[q.category] || groups.motivation).push(q)

  return (
    <div className="card">
      <div className="row between">
        <h2>Screening-call question pack</h2>
        <button className="btn secondary" onClick={regenerate}>Regenerate</button>
      </div>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      {questions.data.length === 0 && (
        <p className="muted">Questions are generated automatically for shortlisted / borderline
          candidates during screening. Use Regenerate to create them now.</p>
      )}
      {Object.entries(groups).map(([category, items]) => items.length > 0 && (
        <div key={category} style={{ marginBottom: 16 }}>
          <h3><Badge value={category} /></h3>
          {items.map((q) => (
            <div key={q.id} style={{ marginBottom: 10 }}>
              <b>{q.question}</b>
              <div className="small muted">Why ask: {q.rationale}</div>
              <textarea rows={1} placeholder="Record the candidate's answer here…"
                        defaultValue={q.answer}
                        onBlur={(e) => e.target.value !== q.answer && saveAnswer(q.id, e.target.value)} />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
function CallDecisionTab({ candidate, reload }) {
  const [decision, setDecision] = useState({ decision: 'shortlist', comments: '', rejection_reason: '' })
  const [call, setCall] = useState({
    call_outcome: 'interested', call_notes: candidate.call_notes || '',
    current_compensation: candidate.current_compensation || '',
    expected_compensation: candidate.expected_compensation || '',
    notice_period: candidate.notice_period || '',
    motivation_notes: candidate.motivation_notes || '',
    communication_rating: candidate.communication_rating || '',
    shift_confirmed: candidate.shift_confirmed, location_confirmed: candidate.location_confirmed,
    proceed_to_hm: false,
  })
  const [message, setMessage] = useState(''); const [error, setError] = useState('')

  const submitDecision = async () => {
    setError('')
    try {
      const r = await api.post(`/api/candidates/${candidate.id}/decision`, decision)
      setMessage(`Decision recorded. AI had recommended "${r.ai_recommendation}" — ${r.agreement ? 'agreement' : 'override'} logged for the audit trail.`)
      reload()
    } catch (e) { setError(e.message) }
  }

  const submitCall = async () => {
    setError('')
    try {
      await api.post(`/api/candidates/${candidate.id}/call-outcome`, call)
      setMessage('Screening-call outcome recorded.')
      reload()
    } catch (e) { setError(e.message) }
  }

  return (
    <div>
      <Alert kind="success" onClose={() => setMessage('')}>{message}</Alert>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>

      <div className="card">
        <h2>Recruiter decision <span className="small muted">(the AI only recommends — you decide)</span></h2>
        {candidate.recruiter_decision && (
          <Alert kind="info">Current decision: <b>{candidate.recruiter_decision}</b>
            {candidate.recruiter_comments && ` — ${candidate.recruiter_comments}`}</Alert>
        )}
        <div className="grid cols-3">
          <label className="field">Decision
            <select value={decision.decision}
                    onChange={(e) => setDecision({ ...decision, decision: e.target.value })}>
              <option value="shortlist">Shortlist</option>
              <option value="hold">Hold</option>
              <option value="reject">Reject</option>
            </select></label>
          <label className="field">Comments
            <input value={decision.comments}
                   onChange={(e) => setDecision({ ...decision, comments: e.target.value })} /></label>
          {decision.decision === 'reject' && (
            <label className="field">Rejection reason * (mandatory)
              <input value={decision.rejection_reason} required
                     onChange={(e) => setDecision({ ...decision, rejection_reason: e.target.value })} /></label>
          )}
        </div>
        <button className="btn" onClick={submitDecision}>Record decision</button>
      </div>

      <div className="card">
        <h2>Screening-call outcome <span className="small muted">(Stage 7 — human recruiter)</span></h2>
        <div className="grid cols-3">
          <label className="field">Outcome
            <select value={call.call_outcome}
                    onChange={(e) => setCall({ ...call, call_outcome: e.target.value })}>
              {['interested', 'not_interested', 'unreachable', 'callback', 'other'].map((x) =>
                <option key={x} value={x}>{x.replaceAll('_', ' ')}</option>)}
            </select></label>
          <label className="field">Current compensation
            <input value={call.current_compensation}
                   onChange={(e) => setCall({ ...call, current_compensation: e.target.value })} /></label>
          <label className="field">Expected compensation
            <input value={call.expected_compensation}
                   onChange={(e) => setCall({ ...call, expected_compensation: e.target.value })} /></label>
          <label className="field">Notice period
            <input value={call.notice_period}
                   onChange={(e) => setCall({ ...call, notice_period: e.target.value })} /></label>
          <label className="field">Communication
            <select value={call.communication_rating}
                    onChange={(e) => setCall({ ...call, communication_rating: e.target.value })}>
              <option value="">—</option>
              {['excellent', 'good', 'average', 'needs improvement'].map((x) =>
                <option key={x} value={x}>{x}</option>)}
            </select></label>
          <label className="field">Shift / location confirmed?
            <span className="row" style={{ fontWeight: 400 }}>
              <label><input type="checkbox" checked={call.shift_confirmed === true}
                            onChange={(e) => setCall({ ...call, shift_confirmed: e.target.checked })} /> shift</label>
              <label><input type="checkbox" checked={call.location_confirmed === true}
                            onChange={(e) => setCall({ ...call, location_confirmed: e.target.checked })} /> location</label>
            </span></label>
        </div>
        <label className="field">Call notes (verify the AI-identified gaps; correct any wrong resume interpretations)
          <textarea value={call.call_notes} onChange={(e) => setCall({ ...call, call_notes: e.target.value })} /></label>
        <label className="field">Motivation notes
          <textarea rows={2} value={call.motivation_notes}
                    onChange={(e) => setCall({ ...call, motivation_notes: e.target.value })} /></label>
        <label className="row" style={{ marginBottom: 12 }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={call.proceed_to_hm}
                 onChange={(e) => setCall({ ...call, proceed_to_hm: e.target.checked })} />
          Confirm: proceed to hiring-manager stage (gate #4)
        </label>
        <button className="btn" onClick={submitCall}>Save call outcome</button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
function SummaryTab({ candidateId }) {
  const summary = useAsync(
    () => api.get(`/api/candidates/${candidateId}/hm-summary`).catch((e) => {
      if (e.status === 404) return null
      throw e
    }), [candidateId])
  const [error, setError] = useState('')

  const generate = () => api.post(`/api/candidates/${candidateId}/hm-summary`)
    .then(() => summary.reload()).catch((e) => setError(e.message))
  const approve = () => api.post(`/api/hm-summaries/${summary.data.id}/approve`)
    .then(() => summary.reload()).catch((e) => setError(e.message))

  if (summary.loading) return <Spinner />
  const s = summary.data

  return (
    <div className="card">
      <div className="row between">
        <h2>Hiring-manager summary {s && <Badge value={s.status} />}</h2>
        <div className="row">
          <button className="btn secondary" onClick={generate}>{s ? 'Regenerate' : 'Generate summary'}</button>
          {s && s.status === 'draft' &&
            <button className="btn" onClick={approve}>Approve & mark shareable ✓</button>}
          {s && <button className="btn secondary"
                        onClick={() => navigator.clipboard.writeText(s.formatted_text)}>Copy for email</button>}
        </div>
      </div>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      {!s && <p className="muted">Generate after the screening call so compensation, notice period and
        your observations are included. Approval (gate #5) is required before sharing.</p>}
      {s && <pre className="profile">{s.formatted_text}</pre>}
    </div>
  )
}

// ---------------------------------------------------------------------------
function EmailsTab({ candidate }) {
  const emails = useAsync(() => api.get(`/api/candidates/${candidate.id}/emails`), [candidate.id])
  const [template, setTemplate] = useState('initial_outreach')
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)

  const act = (fn) => fn().then(() => { setEditing(null); emails.reload() }).catch((e) => setError(e.message))
  const draft = () => act(() => api.post(`/api/candidates/${candidate.id}/emails/draft`, { template_key: template }))

  return (
    <div className="card">
      <div className="row between">
        <h2>Candidate emails</h2>
        <div className="row">
          <select value={template} onChange={(e) => setTemplate(e.target.value)} style={{ width: 260 }}>
            <option value="initial_outreach">Initial outreach</option>
            <option value="more_info_needed">More information needed</option>
            <option value="unreachable">Candidate unreachable</option>
            <option value="reject_not_suitable">Rejection — not suitable (draft-only)</option>
            <option value="hold_future">Hold — retained for future (draft-only)</option>
            <option value="position_on_hold">Position on hold (draft-only)</option>
          </select>
          <button className="btn" onClick={draft}>Draft with AI</button>
        </div>
      </div>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>
      <p className="small muted">Nothing is ever sent without your explicit approval (gate #3).
        Rejection/hold templates are draft-only by policy.</p>

      {emails.loading ? <Spinner /> : emails.data.map((m) => (
        <div key={m.id} className="card" style={{ background: '#fafbfe' }}>
          <div className="row between">
            <div>
              <Badge value={m.status} /> <Badge value={m.template_key} />
              {m.scheduled_for && <span className="small muted"> · scheduled {fmtDate(m.scheduled_for)}</span>}
              {m.sent_at && <span className="small muted"> · sent {fmtDate(m.sent_at)}</span>}
            </div>
            <div className="row">
              {m.status === 'draft' && <>
                <button className="btn sm secondary" onClick={() => setEditing(editing === m.id ? null : m.id)}>
                  {editing === m.id ? 'Close' : 'Edit'}</button>
                <button className="btn sm" onClick={() => act(() => api.post(`/api/emails/${m.id}/approve`))}>Approve</button>
              </>}
              {m.status === 'approved' && !m.sequence_id &&
                <button className="btn sm ok" onClick={() => act(() => api.post(`/api/emails/${m.id}/send`))}>Send now</button>}
              {(m.status === 'draft' || m.status === 'approved') &&
                <button className="btn sm danger" onClick={() => act(() => api.post(`/api/emails/${m.id}/cancel`))}>Cancel</button>}
            </div>
          </div>
          <b>{m.subject}</b> <span className="small muted">→ {m.to_address || 'no address'}</span>
          {editing === m.id
            ? <EmailEditor message={m} onSaved={() => { setEditing(null); emails.reload() }} onError={setError} />
            : <pre className="profile" style={{ marginTop: 8 }}>{m.body}</pre>}
          {m.error && <Alert kind="error">{m.error}</Alert>}
        </div>
      ))}
      {!emails.loading && emails.data.length === 0 &&
        <p className="muted">No emails drafted yet for this candidate.</p>}
    </div>
  )
}

function EmailEditor({ message, onSaved, onError }) {
  const [subject, setSubject] = useState(message.subject)
  const [body, setBody] = useState(message.body)
  const [to, setTo] = useState(message.to_address)
  const save = () => api.put(`/api/emails/${message.id}`, { subject, body, to_address: to })
    .then(onSaved).catch((e) => onError(e.message))
  return (
    <div style={{ marginTop: 8 }}>
      <label className="field">To<input value={to} onChange={(e) => setTo(e.target.value)} /></label>
      <label className="field">Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
      <label className="field">Body<textarea rows={12} value={body} onChange={(e) => setBody(e.target.value)} /></label>
      <button className="btn" onClick={save}>Save (resets approval)</button>
    </div>
  )
}

// ---------------------------------------------------------------------------
function EngagementTab({ candidate, reload }) {
  const sequence = useAsync(
    () => api.get(`/api/candidates/${candidate.id}/sequence`).catch((e) => {
      if (e.status === 404) return null
      throw e
    }), [candidate.id])
  const [offer, setOffer] = useState({
    joining_date: '', reporting_time: '9:00 AM (local office time)',
    induction_link: '', reporting_manager: '', help_contact: '',
  })
  const [message, setMessage] = useState(''); const [error, setError] = useState('')
  const act = (fn, note) => fn().then(() => { setMessage(note); sequence.reload(); reload() })
    .catch((e) => setError(e.message))

  const s = sequence.data
  return (
    <div>
      <Alert kind="success" onClose={() => setMessage('')}>{message}</Alert>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>

      {!s && (
        <div className="card">
          <h2>Mark offer accepted → prepare keep-warm protocol</h2>
          <p className="small muted">Creates the complete schedule: acceptance confirmation,
            every-3rd-day content from the approved library up to T-2 days, T-7 checklist,
            T-5 culture intro, T-3 documentation reminder, T-2 final confirmation,
            T-1 Day-1 instructions and the Day-0 welcome. Nothing activates until you
            approve the sequence (gate #6).</p>
          <div className="grid cols-3">
            <label className="field">Joining date *
              <input type="date" value={offer.joining_date}
                     onChange={(e) => setOffer({ ...offer, joining_date: e.target.value })} /></label>
            <label className="field">Day-1 reporting time
              <input value={offer.reporting_time}
                     onChange={(e) => setOffer({ ...offer, reporting_time: e.target.value })} /></label>
            <label className="field">Video induction link
              <input value={offer.induction_link} placeholder="https://teams…"
                     onChange={(e) => setOffer({ ...offer, induction_link: e.target.value })} /></label>
            <label className="field">Reporting manager
              <input value={offer.reporting_manager}
                     onChange={(e) => setOffer({ ...offer, reporting_manager: e.target.value })} /></label>
            <label className="field">Help contact
              <input value={offer.help_contact}
                     onChange={(e) => setOffer({ ...offer, help_contact: e.target.value })} /></label>
          </div>
          <button className="btn" onClick={() => act(() => api.post(
            `/api/candidates/${candidate.id}/offer-accepted`,
            { ...offer, joining_date: new Date(offer.joining_date + 'T09:00:00Z').toISOString() },
          ), 'Keep-warm schedule prepared — review below and approve to activate.')}
                  disabled={!offer.joining_date}>
            Offer accepted — prepare schedule
          </button>
        </div>
      )}

      {s && (
        <div className="card">
          <div className="row between">
            <h2>Keep-warm sequence <Badge value={s.status} /></h2>
            <div className="row">
              {s.status === 'pending_approval' &&
                <button className="btn" onClick={() => act(() =>
                  api.post(`/api/sequences/${s.id}/approve`), 'Sequence approved and active.')}>Approve & activate ✓</button>}
              {s.status === 'active' &&
                <button className="btn secondary" onClick={() => act(() =>
                  api.post(`/api/sequences/${s.id}/pause`), 'Sequence paused.')}>Pause</button>}
              {s.status === 'paused' &&
                <button className="btn" onClick={() => act(() =>
                  api.post(`/api/sequences/${s.id}/resume`), 'Sequence resumed.')}>Resume</button>}
              {['active', 'paused', 'pending_approval'].includes(s.status) && <>
                <button className="btn danger sm" onClick={() => {
                  const reason = window.prompt('Stop reason (declined / joining date changed / offer withdrawn / other):')
                  if (reason) act(() => api.post(`/api/sequences/${s.id}/stop?reason=${encodeURIComponent(reason)}`), 'Sequence stopped.')
                }}>Stop</button>
              </>}
              {['offer_accepted', 'joined'].includes(candidate.status) &&
                <button className="btn ok" onClick={() => window.confirm(
                  'Confirm handover to the client\'s HR/onboarding team? People IQ automated communication ends here (gate #8).')
                  && act(() => api.post(`/api/candidates/${candidate.id}/handover`), 'Handover confirmed.')}>
                  Confirm Day-1 handover</button>}
            </div>
          </div>
          <p className="small muted">
            Offer accepted {fmtDay(s.offer_accepted_date)} · joining {fmtDay(s.joining_date)}
            {s.stop_reason && <> · stop reason: {s.stop_reason}</>}
          </p>
          <table className="data">
            <thead><tr><th>Send date</th><th>Step</th><th>Subject</th><th>Status</th></tr></thead>
            <tbody>
              {s.emails.map((m) => (
                <tr key={m.id}>
                  <td>{fmtDay(m.scheduled_for)}</td>
                  <td><Badge value={m.step} /></td>
                  <td>{m.subject}</td>
                  <td><Badge value={m.status} />{m.sent_at && <span className="small muted"> {fmtDate(m.sent_at)}</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
function InterviewsTab({ candidateId }) {
  const interviews = useAsync(() => api.get(`/api/candidates/${candidateId}/interviews`), [candidateId])
  const [form, setForm] = useState({ stage: 'Technical interview', interviewer: '', scheduled_at: '' })
  const [transcript, setTranscript] = useState({
    transcript_text: '', candidate_consent: false, interviewer_aware: false,
    transcription_enabled: false, tenant_permission: false,
  })
  const [target, setTarget] = useState(null)
  const [error, setError] = useState(''); const [message, setMessage] = useState('')
  const act = (fn, note) => fn().then(() => { setMessage(note || ''); interviews.reload() })
    .catch((e) => setError(e.message))

  return (
    <div>
      <Alert kind="success" onClose={() => setMessage('')}>{message}</Alert>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>

      <div className="card">
        <h2>Schedule an interview</h2>
        <div className="grid cols-3">
          <label className="field">Stage<input value={form.stage}
            onChange={(e) => setForm({ ...form, stage: e.target.value })} /></label>
          <label className="field">Interviewer<input value={form.interviewer}
            onChange={(e) => setForm({ ...form, interviewer: e.target.value })} /></label>
          <label className="field">Date & time<input type="datetime-local" value={form.scheduled_at}
            onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })} /></label>
        </div>
        <button className="btn" onClick={() => act(() => api.post(
          `/api/candidates/${candidateId}/interviews`,
          { ...form, scheduled_at: form.scheduled_at ? new Date(form.scheduled_at).toISOString() : null },
        ), 'Interview created.')}>Create interview record</button>
      </div>

      {interviews.data?.map((iv) => (
        <div key={iv.id} className="card">
          <div className="row between">
            <h3>{iv.stage} — {iv.interviewer || 'interviewer TBD'}
              {' '}<Badge value={iv.analysis_status} /> <Badge value={iv.review_status} /></h3>
            <div className="row">
              {iv.analysis_status === 'complete' && iv.review_status === 'pending_review' && <>
                <button className="btn sm ok" onClick={() => act(() =>
                  api.post(`/api/interviews/${iv.id}/review`, { approve: true }),
                  'Evaluation approved — it can now be shared (gate #7).')}>Approve evaluation</button>
                <button className="btn sm danger" onClick={() => act(() =>
                  api.post(`/api/interviews/${iv.id}/review`, { approve: false }))}>Reject</button>
              </>}
              <button className="btn sm secondary"
                      onClick={() => setTarget(target === iv.id ? null : iv.id)}>
                {target === iv.id ? 'Close' : iv.has_transcript ? 'Re-upload transcript' : 'Upload transcript'}
              </button>
            </div>
          </div>

          {target === iv.id && (
            <div style={{ marginTop: 10 }}>
              <Alert kind="info">The agent never records or analyses an interview covertly.
                Post-interview analysis requires all four confirmations below (§11 restrictions).</Alert>
              {[['candidate_consent', 'The candidate was notified and consented'],
                ['interviewer_aware', 'The interviewer is aware'],
                ['transcription_enabled', 'Transcription was enabled in the meeting platform'],
                ['tenant_permission', 'Client tenant / administrator permission exists']].map(([k, label]) => (
                <label key={k} className="row" style={{ marginBottom: 4 }}>
                  <input type="checkbox" style={{ width: 'auto' }} checked={transcript[k]}
                         onChange={(e) => setTranscript({ ...transcript, [k]: e.target.checked })} /> {label}
                </label>
              ))}
              <label className="field">Transcript text
                <textarea rows={8} value={transcript.transcript_text}
                          onChange={(e) => setTranscript({ ...transcript, transcript_text: e.target.value })}
                          placeholder="Paste the Teams transcript here…" /></label>
              <button className="btn" onClick={() => act(() =>
                api.post(`/api/interviews/${iv.id}/transcript`, transcript),
                'Transcript analysed — review the evaluation before sharing.')}>
                Upload & analyse (post-interview)</button>
            </div>
          )}

          {iv.analysis && iv.analysis.overall_evaluation && (
            <div style={{ marginTop: 10 }}>
              <h3>Independent AI evaluation — score {iv.analysis.overall_score}/100</h3>
              <p>{iv.analysis.overall_evaluation}</p>
              <div className="grid cols-2">
                <div>
                  <h3>Competency coverage</h3>
                  <table className="data"><thead><tr><th>Competency</th><th>Coverage</th><th>Score</th></tr></thead>
                    <tbody>{(iv.analysis.competencies_covered || []).map((c, i) => (
                      <tr key={i}><td>{c.competency}</td>
                        <td><Badge value={c.coverage} /></td><td>{c.score}/5</td></tr>))}</tbody>
                  </table>
                </div>
                <div>
                  <h3>Vague / unsupported claims</h3>
                  <ul className="clean">{(iv.analysis.vague_or_unsupported_claims || []).map((x, i) =>
                    <li key={i}>{x}</li>)}</ul>
                  <h3>Debrief suggestions</h3>
                  <ul className="clean">{(iv.analysis.debrief_suggestions || []).map((x, i) =>
                    <li key={i}>{x}</li>)}</ul>
                </div>
              </div>
            </div>
          )}

          <div style={{ marginTop: 10 }}>
            <label className="field">Interviewer feedback (recorded separately from the AI)
              <textarea rows={2} defaultValue={iv.interviewer_feedback}
                        onBlur={(e) => e.target.value && e.target.value !== iv.interviewer_feedback &&
                          act(() => api.post(`/api/interviews/${iv.id}/feedback`,
                            { interviewer_feedback: e.target.value }))} /></label>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
function RecordTab({ candidate, reload }) {
  const [fix, setFix] = useState({ correction_note: '' })
  const [status, setStatus] = useState({ status: candidate.status, next_action: candidate.next_action || '' })
  const [message, setMessage] = useState(''); const [error, setError] = useState('')

  const correct = () => api.patch(`/api/candidates/${candidate.id}/correct`, fix)
    .then(() => { setMessage('Correction recorded with a full audit trail.'); reload() })
    .catch((e) => setError(e.message))
  const saveStatus = () => api.patch(`/api/candidates/${candidate.id}/status`, status)
    .then(() => { setMessage('Status updated.'); reload() })
    .catch((e) => setError(e.message))

  return (
    <div>
      <Alert kind="success" onClose={() => setMessage('')}>{message}</Alert>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>

      <div className="card">
        <h2>Correct extracted information</h2>
        <p className="small muted">Fairness control §15 — every correction is logged with who/when/why.</p>
        <div className="grid cols-3">
          {['full_name', 'email', 'phone', 'location', 'current_role', 'current_employer'].map((k) => (
            <label className="field" key={k}>{k.replaceAll('_', ' ')}
              <input placeholder={candidate[k] || '—'}
                     onChange={(e) => setFix({ ...fix, [k]: e.target.value })} /></label>
          ))}
        </div>
        <label className="field">Correction note * (why)
          <input value={fix.correction_note}
                 onChange={(e) => setFix({ ...fix, correction_note: e.target.value })} /></label>
        <button className="btn" onClick={correct} disabled={fix.correction_note.length < 3}>Save correction</button>
        {candidate.correction_note && <pre className="profile">{candidate.correction_note}</pre>}
      </div>

      <div className="card">
        <h2>Pipeline status</h2>
        <div className="grid cols-3">
          <label className="field">Status
            <select value={status.status} onChange={(e) => setStatus({ ...status, status: e.target.value })}>
              {['received', 'screened', 'awaiting_review', 'shortlisted', 'rejected', 'on_hold',
                'screening_call_done', 'submitted_to_hm', 'interview_scheduled', 'interview_complete',
                'offer_made', 'offer_declined', 'offer_withdrawn', 'joined', 'handover_complete',
                'withdrawn', 'unreachable'].map((x) => <option key={x} value={x}>{x.replaceAll('_', ' ')}</option>)}
            </select></label>
          <label className="field">Next action
            <input value={status.next_action}
                   onChange={(e) => setStatus({ ...status, next_action: e.target.value })} /></label>
          {status.status === 'rejected' && (
            <label className="field">Rejection reason *
              <input onChange={(e) => setStatus({ ...status, rejection_reason: e.target.value })} /></label>)}
        </div>
        <p className="small muted">To record an accepted offer use the Keep-warm tab, so the joining
          date and engagement schedule are captured properly.</p>
        <button className="btn" onClick={saveStatus}>Update status</button>
      </div>

      <div className="card">
        <h2>Raw resume text (as extracted)</h2>
        <pre className="profile" style={{ maxHeight: 320, overflow: 'auto' }}>{candidate.resume_text || '—'}</pre>
      </div>
    </div>
  )
}
