<template>
  <div class="monitor-page">
    <!-- 状态栏 -->
    <div class="monitor-status-bar">
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
    </div>

    <!-- LLM 切换面板 -->
    <div v-if="showLlmSettings" class="llm-panel">
      <div class="llm-header">
        <span>模型配置</span>
        <button class="llm-close" @click="showLlmSettings = false" title="关闭">✕</button>
      </div>
      <div class="llm-grid">
        <!-- 切换行 -->
        <div class="llm-row">
          <div class="llm-dropdown" @click.self="closeContextMenu">
            <div class="llm-dropdown-trigger" @click="showDropdown = !showDropdown">
              <span>{{ activeProfile?.name || '选择模型' }}</span>
              <span class="llm-dropdown-model">{{ activeProfile?.model || '' }}</span>
              <span class="llm-dropdown-arrow">{{ showDropdown ? '▲' : '▼' }}</span>
            </div>
            <div v-if="showDropdown" class="llm-dropdown-menu">
              <div v-for="p in profiles" :key="p.id"
                class="llm-dropdown-item"
                :class="{ active: p.is_active }"
                @click="switchToProfile(p)"
                @contextmenu.prevent="onContextMenu($event, p)">
                <span>{{ p.name }}</span>
                <span class="llm-item-model">{{ p.model }}</span>
                <span v-if="p.is_active" class="llm-item-dot">●</span>
              </div>
            </div>
          </div>
          <button class="btn-start" style="background:#444;padding:4px 12px" @click="onAddNew" title="新增配置">+</button>
        </div>
        <!-- 右键菜单 -->
        <div v-if="contextMenu.visible" class="llm-context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }">
          <div v-if="contextMenu.profile?.is_active" class="llm-context-item disabled">当前使用中，无法删除</div>
          <div v-else class="llm-context-item danger" @click="doDeleteContextProfile">删除此配置</div>
        </div>
        <!-- 当前配置展示 -->
        <div class="llm-divider">当前配置</div>
        <div class="llm-info-row"><label>名称</label><span>{{ activeProfile?.name || '—' }}</span></div>
        <div class="llm-info-row"><label>模型</label><span>{{ activeProfile?.model || '—' }}</span></div>
        <div class="llm-info-row"><label>地址</label><span style="font-size:11px">{{ activeProfile?.base_url || '—' }}</span></div>
        <div class="llm-info-row"><label>密钥</label><span>{{ activeProfile?.api_key_set ? '****' : '未设置' }}</span></div>
        <div class="llm-info-row"><label>温度</label><span>{{ activeProfile?.temperature ?? '—' }}</span></div>
        <!-- 新建表单（+ 切换显示） -->
        <template v-if="showAddForm">
          <div class="llm-divider">新建配置</div>
          <div class="llm-row">
            <label>名称</label>
            <input v-model="llmForm.name" class="small-input" placeholder="如 GPT分析" style="flex:1" />
            <label style="margin-left:10px">模型</label>
            <input v-model="llmForm.model" class="small-input" placeholder="gpt-4o / deepseek-chat" style="flex:1" />
          </div>
          <div class="llm-row">
            <label>地址</label>
            <input v-model="llmForm.baseUrl" class="small-input" placeholder="https://api.openai.com/v1" style="flex:1" />
          </div>
          <div class="llm-row">
            <label>密钥</label>
            <input v-model="llmForm.apiKey" class="small-input" type="password" placeholder="sk-..." style="flex:1" />
            <label style="margin-left:10px">温度</label>
            <input v-model.number="llmForm.temperature" class="small-input" type="number" step="0.1" min="0" max="2" style="width:70px" />
          </div>
          <div class="llm-row">
            <button class="btn-start" @click="doSaveProfile">新增配置</button>
          </div>
        </template>
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
                <div class="review-meta">
                  <span v-if="r.agent_review.verdict && !r.agent_review.reasoning.startsWith('[')" class="review-eval" :class="verdictClass(r.agent_review.verdict)">
                    {{ r.agent_review.verdict }}
                  </span>
                  <span v-else-if="r.agent_review.reasoning.startsWith('[')" class="review-eval err">
                    {{ reviewEvalLabel(r) }}
                  </span>
                  <span v-if="r.agent_review.recommendation" class="review-recommend">
                    💡 {{ r.agent_review.recommendation }}
                  </span>
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
  deleteAllDefects, fetchProfiles, createProfile,
  updateProfile, activateProfile, deleteProfile,
} from '../api/client.js'

// ── LLM 多 Profile 切换 ──
const showLlmSettings = ref(false)
const showAddForm = ref(false)
const showDropdown = ref(false)
const llmModel = ref('...')
const llmForm = ref({ name: '', model: '', baseUrl: '', apiKey: '', temperature: 0.3 })
const profiles = ref([])
const activeProfileId = ref('')
const llmMsg = ref('')
const llmOk = ref(true)
const contextMenu = ref({ visible: false, x: 0, y: 0, profile: null })

const activeProfile = computed(() => profiles.value.find(p => p.id === activeProfileId.value))

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
let edgeStatusPoll = null // 始终轮询边端连通状态
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

// ── LLM Profile 管理 ──

async function loadProfiles() {
  try {
    const r = await fetchProfiles()
    profiles.value = r.data
    const active = r.data.find(p => p.is_active)
    if (active) {
      activeProfileId.value = active.id
      llmModel.value = active.model
    }
  } catch {}
}

function onAddNew() {
  showAddForm.value = !showAddForm.value
  if (showAddForm.value) {
    llmForm.value = { name: '', model: '', baseUrl: '', apiKey: '', temperature: 0.3 }
  }
}

function switchToProfile(p) {
  showDropdown.value = false
  if (p.is_active) return
  activateProfile(p.id).then(async r => {
    activeProfileId.value = r.data.id
    llmModel.value = r.data.model
    await loadProfiles()
    llmMsg.value = '已切换至 ' + r.data.name; llmOk.value = true
  }).catch(e => {
    llmMsg.value = '切换失败: ' + (e.response?.data?.detail || e.message); llmOk.value = false
  })
}

function onContextMenu(e, p) {
  contextMenu.value = { visible: true, x: e.clientX, y: e.clientY, profile: p }
}
function closeContextMenu() { contextMenu.value.visible = false }

async function doDeleteContextProfile() {
  const p = contextMenu.value.profile
  contextMenu.value.visible = false
  if (!p || p.is_active) return
  try {
    await deleteProfile(p.id)
    llmMsg.value = '已删除 ' + p.name; llmOk.value = true
    await loadProfiles()
  } catch (e) {
    llmMsg.value = '删除失败: ' + (e.response?.data?.detail || e.message); llmOk.value = false
  }
}

async function doSaveProfile() {
  if (!llmForm.value.model.trim()) { llmMsg.value = '请输入模型名'; llmOk.value = false; return }
  const name = llmForm.value.name.trim() || llmForm.value.model
  try {
    await createProfile({
      name,
      model: llmForm.value.model.trim(),
      base_url: llmForm.value.baseUrl.trim(),
      api_key: llmForm.value.apiKey,
      temperature: llmForm.value.temperature,
    })
    llmMsg.value = '已添加 ' + name; llmOk.value = true
    showAddForm.value = false
    await loadProfiles()
  } catch (e) {
    llmMsg.value = '保存失败: ' + (e.response?.data?.detail || e.message); llmOk.value = false
  }
}

// ── 初始化 ──
onMounted(async () => {
  try { const r = await edgeListCameras(); cameras.value = r.cameras.length ? r.cameras : [0] } catch {}
  try { await loadProfiles() } catch {}
  await refreshDefects()
  cloudPoll = setInterval(refreshDefects, 3000)  // 始终 3s 轮询记录
  edgeStatusPoll = setInterval(async () => {
    try { await edgeStatus(); edgeOk.value = true } catch { edgeOk.value = false }
  }, 2000)  // 始终 2s 轮询边端状态
})

onUnmounted(() => {
  clearInterval(edgePoll)
  clearInterval(edgeStatusPoll)
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
function verdictClass(v) {
  if (v.includes('次品') || v.includes('报废')) return 'ng'
  if (v.includes('合格') || v.includes('放行')) return 'ok'
  return 'pending'
}
</script>
