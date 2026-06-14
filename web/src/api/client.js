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

export function fetchDefects(limit = 30, offset = 0, deviceId = null) {
  const params = { limit, offset }
  if (deviceId) params.device_id = deviceId
  return apiClient.get('/api/v1/defects', { params })
}

// ── 边端 API ──

export async function edgeConfigure(source, conf = 0.3, confEdge = 0.5, videoDir = '') {
  const r = await fetch(`${EDGE_BASE}/api/configure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source, conf, conf_edge: confEdge, video_dir: videoDir }),
  })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error || `配置失败 (${r.status})`)
  return data
}

export function edgeStart() {
  return fetch(`${EDGE_BASE}/api/start`, { method: 'POST' })
    .then(r => r.json().then(data => { if (!r.ok) throw new Error(data.error || `启动失败 (${r.status})`); return data }))
}

export function edgeStop() {
  return fetch(`${EDGE_BASE}/api/stop`, { method: 'POST' })
    .then(r => r.json().then(data => { if (!r.ok) throw new Error(data.error || `停止失败 (${r.status})`); return data }))
}

export function edgeStatus() {
  return fetch(`${EDGE_BASE}/api/status`)
    .then(r => r.json().then(data => { if (!r.ok) throw new Error(data.error || `状态查询失败 (${r.status})`); return data }))
}

export function edgeSummary() {
  return fetch(`${EDGE_BASE}/api/summary`)
    .then(r => r.json().then(data => { if (!r.ok) throw new Error(data.error || `汇总查询失败 (${r.status})`); return data }))
}

export function edgeListFiles() {
  return fetch(`${EDGE_BASE}/api/files`)
    .then(r => r.json().then(data => { if (!r.ok) throw new Error(data.error || `文件列表查询失败 (${r.status})`); return data }))
}

export function edgeListCameras() {
  return fetch(`${EDGE_BASE}/api/cameras`)
    .then(r => r.json().then(data => { if (!r.ok) throw new Error(data.error || `摄像头查询失败 (${r.status})`); return data }))
}

export async function edgeUploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const r = await fetch(`${EDGE_BASE}/api/upload-file`, { method: 'POST', body: form })
  const data = await r.json()
  if (!r.ok || data.ok === false) throw new Error(data.error || `上传失败 (${r.status})`)
  return data
}

export function edgeStreamUrl() {
  return `${EDGE_BASE}/stream`
}

// ── LLM 配置 API ──

export function fetchLlmConfig() {
  return apiClient.get('/api/v1/llm/config')
}

export function updateLlmConfig(data) {
  return apiClient.put('/api/v1/llm/config', data)
}

// ── 缺陷记录操作 ──

export function deleteAllDefects() {
  return apiClient.delete('/api/v1/defects')
}
