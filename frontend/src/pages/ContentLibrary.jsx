import React, { useContext, useState } from 'react'
import { api } from '../api.js'
import { Alert, Badge, Spinner, useAsync } from '../components.jsx'
import { UserContext } from '../App.jsx'

const TYPES = ['leadership_welcome', 'company_video', 'employee_story', 'office_photos',
  'learning_content', 'team_introduction', 'benefits', 'faq', 'shift_info', 'docs_instructions']

export default function ContentLibrary() {
  const user = useContext(UserContext)
  const items = useAsync(() => api.get('/api/content-library'))
  const [form, setForm] = useState({ title: '', content_type: TYPES[0], body: '', url: '' })
  const [error, setError] = useState('')
  const act = (fn) => fn().then(() => items.reload()).catch((e) => setError(e.message))

  return (
    <div>
      <h1>Keep-warm content library</h1>
      <p className="sub">Pre-loaded, approved content used by the every-3rd-day engagement drip
        (§9). Only approved + active items are ever sent to candidates.</p>
      <Alert kind="error" onClose={() => setError('')}>{error}</Alert>

      <div className="card">
        <h2>Add content</h2>
        <div className="grid cols-3">
          <label className="field">Title
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
          <label className="field">Type
            <select value={form.content_type}
                    onChange={(e) => setForm({ ...form, content_type: e.target.value })}>
              {TYPES.map((t) => <option key={t} value={t}>{t.replaceAll('_', ' ')}</option>)}
            </select></label>
          <label className="field">Link (YouTube video, page…)
            <input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></label>
        </div>
        <label className="field">Body text
          <textarea rows={2} value={form.body}
                    onChange={(e) => setForm({ ...form, body: e.target.value })} /></label>
        <button className="btn" disabled={form.title.length < 2}
                onClick={() => act(() => api.post('/api/content-library', form))}>Add to library</button>
      </div>

      <div className="card">
        {items.loading ? <Spinner /> : (
          <table className="data">
            <thead><tr><th>Title</th><th>Type</th><th>Content</th><th>Approved</th><th>Active</th><th></th></tr></thead>
            <tbody>
              {items.data.map((item) => (
                <tr key={item.id}>
                  <td><b>{item.title}</b></td>
                  <td><Badge value={item.content_type} /></td>
                  <td className="small muted">{item.body}<br />
                    {item.url && <a href={item.url} target="_blank" rel="noreferrer">{item.url}</a>}</td>
                  <td>{item.is_approved ? <Badge value="approved" /> : <Badge value="pending_approval" />}</td>
                  <td>{item.is_active ? '✓' : '—'}</td>
                  <td className="row">
                    {!item.is_approved && user.role === 'admin' &&
                      <button className="btn sm" onClick={() => act(() =>
                        api.post(`/api/content-library/${item.id}/approve`))}>Approve</button>}
                    <button className="btn sm secondary" onClick={() => act(() =>
                      api.post(`/api/content-library/${item.id}/toggle-active`))}>
                      {item.is_active ? 'Deactivate' : 'Activate'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
