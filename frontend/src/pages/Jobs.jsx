import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { Alert, Badge, Spinner, useAsync } from '../components.jsx'

const EMPTY = {
  title: '', client_name: 'OculusIT', description: '', location: '',
  working_hours: '', work_model: '', min_experience_years: 0,
  essential_skills: '', preferred_skills: '', qualifications: '',
  compensation_range: '', notice_period_preference: '', mandatory_conditions: '',
  seniority_tier: '', good_enough_note: '', success_criteria: '',
  ideal_candidate_profile: '', domain_context: '',
}

export default function Jobs() {
  const { data: jobs, error, loading, reload } = useAsync(() => api.get('/api/jobs'))
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const toList = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setFormError('')
    try {
      await api.post('/api/jobs', {
        ...form,
        min_experience_years: Number(form.min_experience_years) || 0,
        essential_skills: toList(form.essential_skills),
        preferred_skills: toList(form.preferred_skills),
        mandatory_conditions: toList(form.mandatory_conditions),
      })
      setShowForm(false); setForm(EMPTY); reload()
    } catch (err) { setFormError(err.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="row between">
        <div><h1>Jobs & Screening</h1>
          <p className="sub">Stage 1 — create the requirement, approve the scorecard, then screen.</p></div>
        <button className="btn" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Close' : '+ New job'}
        </button>
      </div>
      {error && <Alert kind="error">{error}</Alert>}

      {showForm && (
        <form className="card" onSubmit={submit}>
          <h2>Create requirement</h2>
          <Alert kind="error">{formError}</Alert>
          <div className="grid cols-2">
            <label className="field">Job title *
              <input value={form.title} onChange={set('title')} required minLength={2} /></label>
            <label className="field">Client
              <input value={form.client_name} onChange={set('client_name')} /></label>
            <label className="field">Location
              <input value={form.location} onChange={set('location')} placeholder="e.g. Gurugram, India" /></label>
            <label className="field">Working hours
              <input value={form.working_hours} onChange={set('working_hours')} placeholder="e.g. 6 PM – 3 AM IST (US EST overlap)" /></label>
            <label className="field">Work model
              <select value={form.work_model} onChange={set('work_model')}>
                <option value="">—</option><option value="remote">Remote</option>
                <option value="hybrid">Hybrid</option><option value="office">Office</option>
              </select></label>
            <label className="field">Minimum experience (years)
              <input type="number" min="0" step="0.5" value={form.min_experience_years}
                     onChange={set('min_experience_years')} /></label>
            <label className="field">Compensation range
              <input value={form.compensation_range} onChange={set('compensation_range')} placeholder="e.g. ₹6–8 LPA" /></label>
            <label className="field">Notice-period preference
              <input value={form.notice_period_preference} onChange={set('notice_period_preference')} placeholder="e.g. 30 days or less" /></label>
            <label className="field">Seniority tier
              <select value={form.seniority_tier} onChange={set('seniority_tier')}>
                <option value="">—</option>
                <option value="entry">Entry (0–2 yrs)</option>
                <option value="associate">Associate (1–3 yrs)</option>
                <option value="mid">Mid</option>
                <option value="senior">Senior</option>
                <option value="lead_plus">Lead / Staff / Principal</option>
              </select></label>
          </div>
          <label className="field">Job description * (paste the full JD)
            <textarea value={form.description} onChange={set('description')} required minLength={20} rows={8} /></label>
          <div className="grid cols-3">
            <label className="field">Essential skills (one per line)
              <textarea value={form.essential_skills} onChange={set('essential_skills')} rows={4} /></label>
            <label className="field">Preferred skills (one per line)
              <textarea value={form.preferred_skills} onChange={set('preferred_skills')} rows={4} /></label>
            <label className="field">Mandatory screening conditions (one per line)
              <textarea value={form.mandatory_conditions} onChange={set('mandatory_conditions')} rows={4}
                        placeholder="e.g. Willingness to work night shift — logistics conditions like shift/WFO/relocation are tracked for the recruiter call, not scored against the candidate" /></label>
          </div>
          <label className="field">Qualification requirements
            <input value={form.qualifications} onChange={set('qualifications')} placeholder="e.g. Bachelor's degree in CS" /></label>

          <h3 style={{ marginTop: 14 }}>Help the AI understand this role in depth</h3>
          <p className="small muted" style={{ marginTop: -8, marginBottom: 12 }}>
            The fields below aren't restated from the JD — they're the context a senior recruiter
            would already have in their head before screening a single resume. The more you fill
            in, the more accurately candidates get judged against what this role actually needs.
          </p>
          <div className="grid cols-2">
            <label className="field">What does "good enough" look like at this level & pay? (helps the AI calibrate expected depth)
              <textarea value={form.good_enough_note} onChange={set('good_enough_note')} rows={3}
                        placeholder="e.g. Solid fundamentals and eagerness to learn — not expected to be an expert at this budget" /></label>
            <label className="field">Success criteria for the first 6–12 months
              <textarea value={form.success_criteria} onChange={set('success_criteria')} rows={3}
                        placeholder="e.g. Independently ships small features with code review by month 3" /></label>
            <label className="field">Example of a strong-fit candidate (real or hypothetical)
              <textarea value={form.ideal_candidate_profile} onChange={set('ideal_candidate_profile')} rows={3}
                        placeholder="e.g. Someone who spent 2 years maintaining a Django app, shipped a few features independently, and can debug production issues without hand-holding" /></label>
            <label className="field">How should industry/domain background be weighed?
              <textarea value={form.domain_context} onChange={set('domain_context')} rows={3}
                        placeholder="e.g. Higher-ed ERP experience is a strong plus but not required — any large-scale enterprise system experience should count as adjacent" /></label>
          </div>
          <button className="btn" disabled={busy}>{busy ? 'Creating…' : 'Create job'}</button>
        </form>
      )}

      {loading ? <Spinner /> : (
        <div className="card">
          <table className="data">
            <thead><tr>
              <th>Code</th><th>Title</th><th>Client</th><th>Location</th>
              <th>Status</th><th>Scorecard</th><th>Candidates</th><th></th>
            </tr></thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.job_code}</td>
                  <td><Link to={`/jobs/${job.id}`}><b>{job.title}</b></Link></td>
                  <td>{job.client_name}</td>
                  <td>{job.location || '—'}</td>
                  <td><Badge value={job.status} /></td>
                  <td>{job.has_approved_scorecard
                    ? <Badge value="approved" /> : <Badge value="pending_approval" />}</td>
                  <td>{job.candidate_count}</td>
                  <td><Link to={`/jobs/${job.id}`}>Open →</Link></td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr><td colSpan={8} className="muted">No jobs yet — create the first requirement.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
