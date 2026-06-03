/// Centralised HTTP client for Baṣīra (Story 8.2, FR-MT-45).
///
/// - Every request sends credentials: 'include' (HttpOnly session cookie).
/// - A 401 response fires a 'basira:unauthorized' event; App.tsx listens and
///   calls POST /auth/logout + recheckAuth() to transition the UI without a
///   hard page reload.
/// - Methods are generic so callers get typed response bodies.
///
/// Usage:
///   import api from './apiClient'
///   const articles = await api.get<Article[]>('/api/articles')

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`)
    this.status = status
    this.detail = detail
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    window.dispatchEvent(new Event('basira:unauthorized'))
    throw new ApiError(401, 'Session expired')
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {}
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const apiClient = {
  get<T>(url: string, signal?: AbortSignal): Promise<T> {
    return fetch(url, { credentials: 'include', signal }).then(handleResponse<T>)
  },

  post<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    }).then(handleResponse<T>)
  },

  put<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return fetch(url, {
      method: 'PUT',
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    }).then(handleResponse<T>)
  },

  del<T>(url: string, signal?: AbortSignal): Promise<T> {
    return fetch(url, {
      method: 'DELETE',
      credentials: 'include',
      signal,
    }).then(handleResponse<T>)
  },

  patch<T>(url: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return fetch(url, {
      method: 'PATCH',
      credentials: 'include',
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    }).then(handleResponse<T>)
  },

  /** Raw fetch for streaming responses or blob downloads (bypasses JSON parsing). */
  raw(url: string, init?: RequestInit): Promise<Response> {
    return fetch(url, { credentials: 'include', ...init })
  },
}

export default apiClient
