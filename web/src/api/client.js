import axios from 'axios'

const EDGE_BASE = import.meta.env.VITE_EDGE_STREAM || 'http://localhost:8080'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    console.error('[API]', err.message)
    return Promise.reject(err)
  },
)

export default apiClient

// ── 云端 API ──

export function fetchDefects(limit = 50) {
  return apiClient.get('/api/v1/defects', { params: { limit } })
}

// ── 边端 API ──

export function edgeConfigure(source, conf = 0.3, confEdge = 0.5, videoDir = '') {
  return fetch(`${EDGE_BASE}/api/configure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, conf, conf_edge: confEdge, video_dir: videoDir }),
  })
}

export function edgeStart() {
  return fetch(`${EDGE_BASE}/api/start`, { method: 'POST' }).then(r => r.json())
}

export function edgeStop() {
  return fetch(`${EDGE_BASE}/api/stop`, { method: 'POST' }).then(r => r.json())
}

export function edgeStatus() {
  return fetch(`${EDGE_BASE}/api/status`).then(r => r.json())
}

export function edgeSummary() {
  return fetch(`${EDGE_BASE}/api/summary`).then(r => r.json())
}

export function edgeListFiles() {
  return fetch(`${EDGE_BASE}/api/files`).then(r => r.json())
}

export function edgeListCameras() {
  return fetch(`${EDGE_BASE}/api/cameras`).then(r => r.json())
}

export async function edgeUploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${EDGE_BASE}/api/upload-file`, {
    method: 'POST',
    body: form,
  })
  return r.json()
}

export function edgeStreamUrl() {
  return `${EDGE_BASE}/stream`
}
