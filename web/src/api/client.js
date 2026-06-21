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
  const params = new URLSearchParams()
  params.append('source', String(source))
  if (conf !== undefined) params.append('conf', String(conf))
  if (confEdge !== undefined) params.append('conf_edge', String(confEdge))
  if (videoDir) params.append('video_dir', videoDir)
  const r = await fetch(`${EDGE_BASE}/api/configure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
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

// ── LLM 配置 API（多 Profile）──

export function fetchLlmConfig() {
  return apiClient.get('/api/v1/llm/config')
}

export function updateLlmConfig(data) {
  return apiClient.put('/api/v1/llm/config', data)
}

export function fetchProfiles() {
  return apiClient.get('/api/v1/llm/profiles')
}

export function createProfile(data) {
  return apiClient.post('/api/v1/llm/profiles', data)
}

export function updateProfile(id, data) {
  return apiClient.put(`/api/v1/llm/profiles/${id}`, data)
}

export function activateProfile(id) {
  return apiClient.post(`/api/v1/llm/profiles/${id}/activate`)
}

export function deleteProfile(id) {
  return apiClient.delete(`/api/v1/llm/profiles/${id}`)
}

// ── 缺陷记录操作 ──

export function deleteAllDefects() {
  return apiClient.delete('/api/v1/defects')
}

// ── 统计 API ──

export function fetchStats(hours = 24) {
  return apiClient.get('/api/v1/stats', { params: { hours } })
}

// ── 系统状态 API ──

export function fetchSystemStatus() {
  return apiClient.get('/api/v1/system/status')
}

// ── 质检报告 API ──

export function fetchReport(defectId) {
  return apiClient.get(`/api/v1/report/${defectId}`)
}

// ── AI 对话 API（SSE） ──

export function chatStream(message, threadId = 'default', onEvent) {
  return fetch('/api/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id: threadId }),
  }).then(async (r) => {
    if (!r.ok) throw new Error(`对话失败 (${r.status})`)
    const reader = r.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { onEvent(JSON.parse(line.slice(6))) } catch {}
        }
      }
    }
  })
}
