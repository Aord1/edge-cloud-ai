<template>
  <div class="monitor-page">
    <header class="top-bar">
      <h1>边云协同检测</h1>
      <div class="top-status">
        <span class="top-model" @click="showLlmSettings = !showLlmSettings" title="切换模型">
          🤖 {{ llmModel }}
        </span>
        <span><span class="dot" :class="edgeOk ? 'on' : 'off'"></span>边缘端</span>
        <span><span class="dot" :class="cloudOk ? 'on' : 'off'"></span>云端</span>
        <span v-if="fps > 0">{{ fps }}fps</span>
      </div>
    </header>

    <!-- LLM 切换面板 -->
    <div v-if="showLlmSettings" class="llm-panel">
      <div class="llm-row">
        <label>模型</label>
        <select v-model="llmForm.model" class="small-select">
          <option value="gpt-4o">GPT-4o (OpenAI)</option>
          <option value="gpt-4o-mini">GPT-4o-mini (OpenAI)</option>
          <option value="deepseek-chat">DeepSeek V3</option>
          <option value="deepseek-reasoner">DeepSeek R1</option>
          <option value="qwen-plus">通义千问 Plus</option>
          <option value="qwen-max">通义千问 Max</option>
          <option value="moonshot-v1-8k">Moonshot (Kimi)</option>
          <option value="__custom__">自定义...</option>
        </select>
        <input v-if="llmForm.model === '__custom__'" v-model="llmForm.customModel" class="small-input" placeholder="模型名称" style="width:160px" />
      </div>
      <div class="llm-row">
        <label>地址</label>
        <input v-model="llmForm.baseUrl" class="small-input" placeholder="留空=OpenAI 官方" style="flex:1" />
      </div>
      <div class="llm-row">
        <label>密钥</label>
        <input v-model="llmForm.apiKey" class="small-input" type="password" placeholder="sk-..." style="flex:1" />
      </div>
      <div class="llm-row">
        <label>温度</label>
        <input v-model.number="llmForm.temperature" class="small-input" type="number" step="0.1" min="0" max="2" style="width:70px" />
        <button class="btn-start" @click="doSwitchLlm" style="margin-left:auto">切换</button>
      </div>
      <div v-if="llmMsg" class="llm-msg" :class="llmOk ? 'ok' : 'err'">{{ llmMsg }}</div>
    </div>

    <div class="monitor-body">
      <!-- 左：控制 + 视频 -->
      <section class="stream-section">
        <div class="control-panel">
          <!-- 摄像头模式 -->
          <div class="control-row">
            <label class="radio-label">
              <input type="radio" value="camera" v-model="sourceType" :disabled="running" />
              摄像头
            </label>
            <template v-if="sourceType === 'camera'">
              <select v-model="cameraId" class="small-select" :disabled="running">
                <option v-for="c in cameras" :key="c" :value="String(c)">{{ c }}</option>
                <option value="__custom__">自定义...</option>
              </select>
              <input
                v-if="cameraId === '__custom__'"
                v-model="customSource"
                class="small-input"
                placeholder="摄像头索引或设备路径"
                style="width:200px"
                :disabled="running"
              />
            </template>
          </div>

          <!-- 文件模式 -->
          <div class="control-row">
            <label class="radio-label">
              <input type="radio" value="file" v-model="sourceType" :disabled="running" />
              视频文件
            </label>
            <template v-if="sourceType === 'file'">
              <label class="file-pick-btn" :class="{ disabled: running }">
                <input
                  type="file"
                  accept="video/*,image/*"
                  @change="onFilePicked"
                  :disabled="running || uploading"
                  style="display:none"
                />
                📁 选择文件
              </label>
              <span v-if="fileSource" class="file-name">{{ fileName }}</span>
              <span v-if="uploading" class="upload-status"><span class="spinner"></span> 上传中...</span>
            </template>
          </div>

          <div class="control-row">
            <label>置信度</label>
            <input v-model.number="confidence" class="small-input" type="number" step="0.05" min="0.1" max="0.9" style="width:60px" :disabled="running" />
            <button v-if="!running" class="btn-start" @click="doStart" :disabled="starting || !canStart">{{ starting ? '启动中...' : '▶ 开始' }}</button>
            <button v-else class="btn-stop" @click="doStop" :disabled="stopping">■ 停止</button>
          </div>
          <div v-if="error" class="error-bar">{{ error }}</div>
        </div>

        <div class="video-box">
          <img v-if="running" :src="streamUrl" alt="Stream" />
          <div v-else class="video-placeholder">
            <div class="placeholder-icon">⏸</div>
            <div>选择摄像头或视频文件，点击「开始」</div>
          </div>
        </div>
      </section>

      <!-- 右：记录 + 复核 -->
      <section class="feed-section">
        <div class="feed-header">
          <div class="feed-title">检测记录 &amp; Agent 复核</div>
          <div class="feed-summary" v-if="records.length">
            {{ records.length }} 条 &middot; 已复核 {{ reviewedCount }}
            <span v-if="reviewingCount"> &middot; 复核中 {{ reviewingCount }}</span>
          </div>
        </div>

        <div class="feed-list" ref="feedList">
          <div v-if="!records.length" class="feed-empty">等待检测结果...</div>
          <div v-for="r in records" :key="r.id" class="feed-item" :class="{ expanded: expanded === r.id }">
            <div class="defect-row" @click="r.decision === 'CLOUD' && toggleExpand(r.id)">
              <div class="defect-left">
                <span class="defect-dot" :class="r.decision === 'CLOUD' ? 'cloud' : 'edge'"></span>
                <span class="defect-time">{{ fmtTime(r.created_at) }}</span>
                <span class="defect-types">{{ names(r.detections) }}</span>
                <span class="defect-conf">{{ (r.avg_confidence * 100).toFixed(0) }}%</span>
              </div>
              <div class="defect-right">
                <span class="tag" :class="r.decision === 'CLOUD' ? 'tag-cloud' : 'tag-edge'">
                  {{ r.decision === 'CLOUD' ? '复核' : '本地' }}
                </span>
                <span v-if="r.decision === 'CLOUD'" class="expand-arrow">{{ expanded === r.id ? '▾' : '▸' }}</span>
              </div>
            </div>
            <div v-if="expanded === r.id" class="review-panel">
              <div v-if="r.agent_review" class="review-content">
                <div class="review-label">Agent 复核</div>
                <div class="review-text">{{ r.agent_review.reasoning }}</div>
                <div v-if="r.agent_review.tool_calls?.length" class="review-tools">
                  🔧 {{ r.agent_review.tool_calls.map(t => t.tool).join(', ') }}
                </div>
              </div>
              <div v-else class="review-content review-pending">
                <span class="spinner"></span> Agent 复核中...
              </div>
            </div>
          </div>
        </div>

        <div v-if="!running && records.length" class="summary-bar">
          <span>检测完成</span>
          <span>总 {{ records.length }}</span>
          <span>云端复核 {{ cloudCount }}</span>
          <span>本地 {{ edgeCount }}</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  edgeConfigure, edgeStart, edgeStop, edgeStatus, edgeStreamUrl, edgeSummary,
  edgeListFiles, edgeListCameras, edgeUploadFile, fetchDefects,
  fetchLlmConfig, updateLlmConfig,
} from '../api/client.js'

// ── LLM 切换 ──
const showLlmSettings = ref(false)
const llmModel = ref('gpt-4o')
const llmForm = ref({ model: 'gpt-4o', customModel: '', baseUrl: '', apiKey: '', temperature: 0.3 })
const llmMsg = ref('')
const llmOk = ref(true)

// ── 源选择 ──
const sourceType = ref('camera')
const cameras = ref([0])
const cameraId = ref('0')
const customSource = ref('')
const fileSource = ref('')
const fileName = ref('')
const uploading = ref(false)
const confidence = ref(0.3)
const running = ref(false)
const starting = ref(false)
const stopping = ref(false)
const error = ref('')

const canStart = computed(() => {
  if (sourceType.value === 'camera') {
    if (cameraId.value === '__custom__') return !!customSource.value.trim()
    return !!cameraId.value
  }
  return !!fileSource.value
})

const streamUrl = computed(() => edgeStreamUrl())

// ── 状态 ──
const edgeOk = ref(false)
const cloudOk = ref(false)
const fps = ref(0)
const records = ref([])
const expanded = ref(null)
let edgePoll = null
let cloudPoll = null
let edgeRecordPoll = null

const cloudCount = computed(() => records.value.filter(r => r.decision === 'CLOUD').length)
const edgeCount = computed(() => records.value.filter(r => r.decision === 'EDGE').length)
const reviewedCount = computed(() => records.value.filter(r => r.agent_review).length)
const reviewingCount = computed(() => records.value.filter(r => r.decision === 'CLOUD' && !r.agent_review).length)

// ── 初始化 ──
onMounted(async () => {
  try { const r = await edgeListCameras(); cameras.value = r.cameras.length ? r.cameras : [0] } catch {}
  try { const r = await fetchLlmConfig(); applyLlmConfig(r.data) } catch {}
})

// ── LLM 预设地址 ──
const LLM_PRESETS = {
  'gpt-4o': 'https://api.openai.com/v1',
  'gpt-4o-mini': 'https://api.openai.com/v1',
  'deepseek-chat': 'https://api.deepseek.com/v1',
  'deepseek-reasoner': 'https://api.deepseek.com/v1',
  'qwen-plus': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  'qwen-max': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  'moonshot-v1-8k': 'https://api.moonshot.cn/v1',
}

function applyLlmConfig(data) {
  llmModel.value = data.model || 'gpt-4o'
  llmForm.value = {
    model: Object.keys(LLM_PRESETS).includes(data.model) ? data.model : '__custom__',
    customModel: Object.keys(LLM_PRESETS).includes(data.model) ? '' : data.model,
    baseUrl: data.base_url || '',
    apiKey: data.api_key || '',
    temperature: data.temperature ?? 0.3,
  }
}

async function doSwitchLlm() {
  const model = llmForm.value.model === '__custom__' ? llmForm.value.customModel.trim() : llmForm.value.model
  if (!model) { llmMsg.value = '请输入模型名称'; llmOk.value = false; return }

  const baseUrl = llmForm.value.model === '__custom__'
    ? llmForm.value.baseUrl
    : (llmForm.value.baseUrl || LLM_PRESETS[llmForm.value.model] || '')

  try {
    const r = await updateLlmConfig({
      model,
      base_url: baseUrl,
      api_key: llmForm.value.apiKey || undefined,
      temperature: llmForm.value.temperature,
    })
    applyLlmConfig(r.data)
    llmModel.value = model
    llmMsg.value = `已切换至 ${model}`
    llmOk.value = true
  } catch (e) {
    llmMsg.value = '切换失败: ' + (e.response?.data?.detail || e.message)
    llmOk.value = false
  }
}

// ── 文件选择 ──
async function onFilePicked(e) {
  const file = e.target.files?.[0]
  if (!file) return
  fileName.value = file.name
  uploading.value = true
  fileSource.value = ''
  try {
    const r = await edgeUploadFile(file)
    if (r.ok) {
      fileSource.value = r.path
      fileName.value = `${r.name} (${r.size_mb}MB)`
    } else {
      fileName.value = '上传失败: ' + r.error
    }
  } catch (err) {
    fileName.value = '上传失败'
  }
  uploading.value = false
}

// ── 操作 ──
async function doStart() {
  starting.value = true
  let src
  if (sourceType.value === 'camera') {
    src = cameraId.value === '__custom__' ? customSource.value.trim() : cameraId.value
  } else {
    src = fileSource.value
  }
  if (!src) { starting.value = false; return }
  error.value = ''
  try {
    await edgeConfigure(src, confidence.value)
    const r = await edgeStart()
    if (r.ok) {
      running.value = true
      records.value = []
      expanded.value = null
      startPolling()
    } else {
      error.value = r.error || '启动失败'
    }
  } catch (e) {
    error.value = '无法连接边缘端，请确认 python -m edge.main --server 已启动'
    console.error(e)
  }
  starting.value = false
}

async function doStop() {
  stopping.value = true
  try { await edgeStop() } catch {}
  running.value = false
  stopping.value = false
  stopPolling()
  setTimeout(async () => {
    await refreshEdgeRecords()
    await refreshDefects()
  }, 1500)
}

function toggleExpand(id) {
  expanded.value = expanded.value === id ? null : id
}

// ── 轮询 ──
function startPolling() {
  edgePoll = setInterval(async () => {
    try {
      const s = await edgeStatus()
      edgeOk.value = true
      fps.value = s.fps || 0
      if ((s.state === 'stopped' || s.state === 'stopping') && running.value) {
        running.value = false
        stopPolling()
        await refreshEdgeRecords()
        await refreshDefects()
        mergeAllRecords()
      }
    } catch { edgeOk.value = false }
  }, 1000)
  cloudPoll = setInterval(refreshDefects, 2000)
  edgeRecordPoll = setInterval(refreshEdgeRecords, 3000)
}

function stopPolling() {
  clearInterval(edgePoll)
  clearInterval(cloudPoll)
  clearInterval(edgeRecordPoll)
}

const _cloudList = ref([])
const _edgeList = ref([])

async function refreshDefects() {
  try {
    const res = await fetchDefects(50)
    cloudOk.value = true
    _cloudList.value = res.data.map(r => ({ ...r, decision: r.decision || 'CLOUD' }))
  } catch { cloudOk.value = false }
  mergeAllRecords()
}

async function refreshEdgeRecords() {
  try {
    const r = await edgeSummary()
    _edgeList.value = (r.records || []).map((item, i) => ({
      id: `edge_${i}`,
      device_id: '',
      reason: item.reason || '',
      detections: (item.defect_types || []).map(t => ({ class_name: t })),
      avg_confidence: item.avg_confidence ?? 0,
      inference_ms: 0,
      agent_review: null,
      decision: item.decision || 'EDGE',
      created_at: item.time ? `2000-01-01T${item.time}` : new Date().toISOString(),
    }))
  } catch {}
  mergeAllRecords()
}

function mergeAllRecords() {
  const merged = [..._edgeList.value, ..._cloudList.value]
  merged.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
  records.value = merged
}

// ── 格式化 ──
function names(d) { return d?.map(x => x.class_name).join(', ') || '' }
function fmtTime(t) { return t ? new Date(t).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', second:'2-digit' }) : '' }

onUnmounted(stopPolling)
</script>
