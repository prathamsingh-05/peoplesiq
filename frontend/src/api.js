// Thin API client. The JWT lives in sessionStorage (cleared when the tab
// closes) — an internal-tool tradeoff between UX and exposure.
const TOKEN_KEY = 'peopleiq_token'

export function getToken() { return sessionStorage.getItem(TOKEN_KEY) }
export function setToken(token) { sessionStorage.setItem(TOKEN_KEY, token) }
export function clearToken() { sessionStorage.removeItem(TOKEN_KEY) }

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
  }
}

async function request(path, { method = 'GET', body, formData } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const response = await fetch(path, {
    method,
    headers,
    body: formData ? formData : body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (response.status === 401 && !path.endsWith('/login')) {
    clearToken()
    window.location.hash = '#/login'
    throw new ApiError(401, 'Session expired')
  }
  if (!response.ok) {
    let detail = response.statusText
    try { detail = (await response.json()).detail ?? detail } catch { /* noop */ }
    throw new ApiError(response.status, detail)
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) return response.json()
  return response
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  postForm: (path, formData) => request(path, { method: 'POST', formData }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  patch: (path, body) => request(path, { method: 'PATCH', body }),
  del: (path) => request(path, { method: 'DELETE' }),
}

export async function downloadFile(path, fallbackName) {
  const response = await request(path)
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/)
  const anchor = document.createElement('a')
  anchor.href = URL.createObjectURL(blob)
  anchor.download = match ? match[1] : fallbackName
  anchor.click()
  URL.revokeObjectURL(anchor.href)
}
