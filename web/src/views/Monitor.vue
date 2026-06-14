<template>
  <div class="monitor-page">
    <header class="top-bar">
      <h1>边云协同检测</h1>
      <div class="top-status">
        <span class="top-model" @click="showLlmSettings = !showLlmSettings" title="切换模型">
          🤖 {{ llmModel }}
        </span>
        <span class="conn-badge" :class="edgeOk ? 'up' : 'down'">
          <span class="dot" :class="edgeOk ? 'on' : 'off'"></span>边缘{{ edgeOk ? '' : '离线' }}
        </span>
        <span class="conn-badge" :class="cloudOk ? 'up' : 'down'">
          <span class="dot" :class="cloudOk ? 'on' : 'off'"></span>云端{{ cloudOk ? '' : '离线' }}
        </span>
        <span v-if="fps > 0" class="fps-badge">{{ fps }}fps</span>
        <span class="refresh-dot" title="每3秒自动刷新">◉</span>
      </div>
    </header>

    <!-- LLM 切换面板 -->
    <div v-if="showLlmSettings" class="llm-panel">
      <div class="llm-header">
        <span>模型设置</span>
        <button class="llm-close" @click="showLlmSettings = false" title="关闭">✕</button>
      </div>
      <div class="llm-grid">
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
          <input v-if="llmForm.model === '__custom__'" v-model="llmForm.customModel" class="small-input" placeholder="模型名称" style="width:140px" />
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
          <button class="btn-start" @click="doSwitchLlm">切换</button>
        </div>
      </div>
      <div v-if="llmMsg" class="llm-msg" :class="llmOk ? 'ok' : 'err'">{{ llmMsg }}</div>
    </div>

    <div class="monitor-body">
      <!-- 左：控制 + 视频 -->
      <section class="stream-section">
        <div class="control-panel">
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
              <input v-if="cameraId === '__custom__'" v-model="customSource" class="small-input" placeholder="摄像头索引或设备路径" style="width:200px" :disabled="running" />
            </template>
          </div>
          <div class="control-row">
            <label class="radio-label">
              <input type="radio" value="file" v-model="sourceType" :disabled="running" />
              视频文件
            </label>
            <template v-if="sourceType === 'file'">
              <label class="file-pick-btn" :class="{ disabled: running }">
                <input type="file" accept="video/*,image/*" @change="onFilePicked" :disabled="running || uploading" style="display:none" />
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

      <!-- 右：检测记录 + Agent 复核 -->
      <section class="feed-section">
        <div class="feed-header">
          <div class="feed-title">检测记录 &amp; Agent 复核</div>
          <div class="feed-summary">
            <span class="summary-chip">共 {{ totalRecords }} 条</span>
            <span class="summary-chip chip-edge">本地 {{ edgeCount }}</span>
            <span class="summary-chip chip-cloud">复核 {{ cloudCount }}</span>
            <button class="btn-refresh" @click="refreshDefects" :disabled="loading" title="刷新">🔄</button>
            <button class="btn-delete" @click="doDeleteAll" :disabled="deleting || !totalRecords" title="清空所有记录">
              {{ deleting ? '删除中...' : '🗑 清空' }}
            </button>
          </div>
          <div v-if="lastUpdated" class="feed-update">更新于 {{ fmtTime(lastUpdated) }}</div>
        </div>

        <div class="feed-list" ref="feedList">
          <div v-if="loading && !records.length" class="feed-empty">
            <span class="spinner"></span>
            <div>加载记录中...</div>
          </div>
          <div v-else-if="!records.length" class="feed-empty">
            <div class="placeholder-icon">📋</div>
            <div>暂无检测记录</div>
          </div>
          <div v-for="r in records" :key="r.id" class="feed-item" :class="{ 'feed-item-cloud': r.decision === 'CLOUD' }">
            <div class="defect-row" @click="showImage = showImage === r.id ? null : r.id">
              <img
                v-if="r.image_path"
                :src="imageUrl(r.id)"
                class="defect-thumb"
                @click.stop="showImage = showImage === r.id ? null : r.id"
                title="点击查看大图"
              />
              <div class="defect-left">
                <span class="defect-time">{{ fmtTime(r.created_at) }}</span>
                <span class="defect-types" :title="names(r.detections)">{{ names(r.detections) }}</span>
                <span class="defect-count" v-if="r.detections?.length">{{ r.detections.length }}处</span>
                <span class="defect-reason">{{ cnReason(r.reason) }}</span>
              </div>
              <div class="defect-right">
                <span class="defect-conf">{{ (r.avg_confidence * 100).toFixed(0) }}%</span>
                <span class="tag" :class="r.decision === 'CLOUD' ? 'tag-cloud' : 'tag-edge'">
                  {{ r.decision === 'CLOUD' ? '复核' : '本地' }}
                </span>
                <span v-if="r.decision === 'CLOUD'" class="review-badge" :class="reviewStatus(r)" :title="reviewTitle(r)">
                  {{ reviewIcon(r) }}
                </span>
              </div>
            </div>
            <!-- 大图预览 -->
            <div v-if="showImage === r.id" class="image-preview" @click="showImage = null">
              <img :src="imageUrl(r.id)" />
            </div>
            <!-- Agent 复核结果 -->
            <div v-if="r.decision === 'CLOUD'" class="review-inline">
              <div v-if="r.agent_review?.reasoning" class="review-content">
                <div v-if="r.agent_review.reasoning.startsWith('[')" class="review-eval err">
                  {{ reviewEvalLabel(r) }}
                </div>
                <div v-else class="review-eval" :class="r.agent_review.evaluation === 'NG' ? 'ng' : 'ok'">
                  {{ r.agent_review.evaluation || '复核完成' }}
                </div>
                <div class="review-text">{{ r.agent_review.reasoning }}</div>
                <div v-if="r.agent_review.reasoning.includes('未配置')" class="review-hint">
                  💡 点击右上角 🤖 图标配置 API Key
                </div>
              </div>
              <div v-else class="review-content review-pending">
                <span class="spinner"></span> 等待 Agent 复核...
              </div>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="pagination">
          <span class="page-info">第 {{ page }}/{{ totalPages }} 页</span>
          <button :disabled="page <= 1" @click="goPage(1)" title="首页">⟪</button>
          <button :disabled="page <= 1" @click="goPage(page - 1)">←</button>
          <span v-for="p in visiblePages" :key="p">
            <button v-if="p === '...'" disabled class="page-ellipsis">...</button>
            <button v-else :class="{ active: p === page }" @click="goPage(p)">{{ p }}</button>
          </span>
          <button :disabled="page >= totalPages" @click="goPage(page + 1)">→</button>
          <button :disabled="page >= totalPages" @click="goPage(totalPages)" title="末页">⟫</button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  edgeConfigure, edgeStart, edgeStop, edgeStatus, edgeStreamUrl,
  edgeListCameras, edgeUploadFile, fetchDefects,
  fetchLlmConfig, updateLlmConfig, deleteAllDefects,
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
const totalRecords = ref(0)
const loading = ref(false)
const deleting = ref(false)
const showImage = ref(null)
const page = ref(1)
const pageSize = 30
const lastUpdated = ref(null)
let edgePoll = null
let cloudPoll = null

const totalPages = computed(() => Math.max(1, Math.ceil(totalRecords.value / pageSize)))
const edgeCount = computed(() => records.value.filter(r => r.decision !== 'CLOUD').length)
const cloudCount = computed(() => records.value.filter(r => r.decision === 'CLOUD').length)

const visiblePages = computed(() => {
  const tp = totalPages.value
  const p = page.value
  if (tp <= 7) return Array.from({ length: tp }, (_, i) => i + 1)
  const pages = []
  if (p > 3) pages.push(1, '...')
  for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) pages.push(i)
  if (p < tp - 2) pages.push('...', tp)
  return pages
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
    apiKey: data.api_key_set ? '****' : '',
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

// ── 初始化 ──
onMounted(async () => {
  try { const r = await edgeListCameras(); cameras.value = r.cameras.length ? r.cameras : [0] } catch {}
  try { const r = await fetchLlmConfig(); applyLlmConfig(r.data) } catch {}
  await refreshDefects()
  cloudPoll = setInterval(refreshDefects, 3000)  // 始终 3s 轮询记录
})

onUnmounted(() => {
  clearInterval(edgePoll)
  clearInterval(cloudPoll)
})

// ── 分页 ──
function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  refreshDefects()
}

async function refreshDefects() {
  loading.value = true
  try {
    const res = await fetchDefects(pageSize, (page.value - 1) * pageSize)
    cloudOk.value = true
    totalRecords.value = res.data.total
    records.value = res.data.items
    lastUpdated.value = new Date()
  } catch { cloudOk.value = false }
  loading.value = false
}

async function doDeleteAll() {
  if (!confirm('确认删除所有检测记录？此操作不可撤销。')) return
  deleting.value = true
  try {
    await deleteAllDefects()
    totalRecords.value = 0
    records.value = []
    page.value = 1
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.detail || e.message))
  }
  deleting.value = false
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
    if (r.ok) { fileSource.value = r.path; fileName.value = `${r.name} (${r.size_mb}MB)` }
    else fileName.value = '上传失败: ' + r.error
  } catch { fileName.value = '上传失败' }
  uploading.value = false
}

// ── 操作 ──
async function doStart() {
  starting.value = true
  let src = sourceType.value === 'camera'
    ? (cameraId.value === '__custom__' ? customSource.value.trim() : cameraId.value)
    : fileSource.value
  if (!src) { starting.value = false; return }
  error.value = ''
  try {
    await edgeConfigure(src, confidence.value)
    const r = await edgeStart()
    if (r.ok) {
      running.value = true
      records.value = []
      startPolling()
    } else {
      error.value = r.error || '启动失败'
    }
  } catch {
    error.value = '无法连接边缘端，请确认 python -m edge.main --server 已启动'
  }
  starting.value = false
}

async function doStop() {
  stopping.value = true
  try { await edgeStop() } catch {}
  running.value = false
  stopping.value = false
  stopPolling()
}

// ── 轮询（仅状态） ──
let edgeFailCount = 0
function startPolling() {
  edgeFailCount = 0
  edgePoll = setInterval(async () => {
    try {
      const s = await edgeStatus()
      edgeOk.value = true
      edgeFailCount = 0
      fps.value = s.fps || 0
      if ((s.state === 'stopped' || s.state === 'stopping') && running.value) {
        running.value = false
        stopPolling()
      }
    } catch {
      edgeOk.value = false
      edgeFailCount++
      if (edgeFailCount >= 3 && running.value) {
        running.value = false
        stopPolling()
      }
    }
  }, 1000)
}

function stopPolling() {
  clearInterval(edgePoll)
  setTimeout(refreshDefects, 2000)
}

// ── 格式化 ──
const CLASS_CN = {
  crazing: '裂纹', inclusion: '夹杂', patches: '斑块',
  pitted_surface: '麻点', rolled_in_scale: '氧化皮', scratches: '划痕',
  'rolled-in_scale': '氧化皮',
}
const REASON_CN = {
  review: '需复核', mixed_defects: '混杂缺陷', crowded: '缺陷过多',
  simple: '高置信本地', empty: '无缺陷', no_defect: '无效',
  low_confidence: '低置信', severe: '严重缺陷', mqtt: 'MQTT上传',
}
function toCn(name) { return CLASS_CN[name] || name }
function cnReason(r) { return REASON_CN[r] || r || '' }
function names(d) { return d?.map(x => toCn(x.class_name)).join(', ') || '' }
function fmtTime(t) { return t ? new Date(t).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', second:'2-digit' }) : '' }
function imageUrl(id) { return `/api/v1/defects/${id}/image` }
function reviewStatus(r) {
  const text = r.agent_review?.reasoning || ''
  if (text.startsWith('[')) return 'err'
  if (text) return 'done'
  return 'pending'
}
function reviewIcon(r) {
  const text = r.agent_review?.reasoning || ''
  if (text.includes('未配置')) return '⚠'
  if (text.includes('调用失败')) return '✗'
  if (text.includes('无输出')) return '?'
  if (text) return '✓'
  return '⏳'
}
function reviewTitle(r) {
  const text = r.agent_review?.reasoning || ''
  if (text.includes('未配置')) return '未配置 API Key，请点击右上角🤖配置'
  if (text.includes('调用失败')) return 'Agent 调用失败'
  if (text.includes('无输出')) return 'Agent 未返回内容'
  if (text) return '复核完成'
  return '等待 Agent 复核中...'
}
function reviewEvalLabel(r) {
  const text = r.agent_review?.reasoning || ''
  if (text.includes('未配置')) return '未配置'
  if (text.includes('调用失败')) return '调用失败'
  if (text.includes('无输出')) return '无输出'
  return '异常'
}
</script>
