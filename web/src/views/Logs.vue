<template>
  <div class="page-container">
    <div class="page-header">
      <h2>质检日志</h2>
      <div class="header-controls">
        <button class="btn-refresh" @click="refresh" :disabled="loading">🔄 刷新</button>
        <span v-if="lastUpdated" class="update-time">更新于 {{ fmtTime(lastUpdated) }}</span>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-row">
        <label>缺陷类型</label>
        <select v-model="filterType" class="small-select" @change="refresh">
          <option value="">全部</option>
          <option v-for="c in CLASS_LIST" :key="c" :value="c">{{ cnName(c) }}</option>
        </select>
        <label>判定结果</label>
        <select v-model="filterDecision" class="small-select" @change="refresh">
          <option value="">全部</option>
          <option value="EDGE">本地判定</option>
          <option value="CLOUD">云端复核</option>
        </select>
        <label>复核状态</label>
        <select v-model="filterReview" class="small-select" @change="refresh">
          <option value="">全部</option>
          <option value="done">已复核</option>
          <option value="pending">待复核</option>
        </select>
        <button class="btn-clear-filter" @click="clearFilters">清除筛选</button>
      </div>
    </div>

    <!-- 统计 -->
    <div class="log-summary">
      <span>共 {{ totalRecords }} 条记录</span>
      <span v-if="filteredCount !== totalRecords">（筛选后 {{ filteredCount }} 条）</span>
    </div>

    <!-- 记录表格 -->
    <div class="log-table-wrap">
      <div v-if="loading && !records.length" class="loading-box"><span class="spinner"></span> 加载中...</div>
      <div v-else-if="!filteredRecords.length" class="loading-box">暂无匹配记录</div>
      <table v-else class="log-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>设备</th>
            <th>缺陷类型</th>
            <th>数量</th>
            <th>置信度</th>
            <th>判定</th>
            <th>复核状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filteredRecords" :key="r.id" :class="{ 'row-cloud': r.decision === 'CLOUD' }">
            <td class="cell-time">{{ fmtTime(r.created_at) }}</td>
            <td class="cell-device">{{ r.device_id }}</td>
            <td class="cell-types">{{ names(r.detections) }}</td>
            <td>{{ r.detections?.length || 0 }}</td>
            <td class="cell-conf">{{ (r.avg_confidence * 100).toFixed(0) }}%</td>
            <td><span class="tag" :class="r.decision === 'CLOUD' ? 'tag-cloud' : 'tag-edge'">{{ r.decision === 'CLOUD' ? '复核' : '本地' }}</span></td>
            <td>
              <span v-if="r.decision === 'CLOUD'" class="review-badge" :class="reviewStatus(r)" :title="reviewTitle(r)">{{ reviewIcon(r) }}</span>
              <span v-else class="text-muted">—</span>
            </td>
            <td>
              <button class="btn-view" @click="viewDetail(r)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>
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

    <!-- 详情弹窗 -->
    <div v-if="detailRow" class="modal-overlay" @click="detailRow = null">
      <div class="modal-box" @click.stop>
        <div class="modal-header">
          <span>缺陷详情</span>
          <button class="llm-close" @click="detailRow = null">✕</button>
        </div>
        <div class="modal-body">
          <img v-if="detailRow.image_path" :src="imageUrl(detailRow.id)" class="modal-image" />
          <div class="modal-info">
            <div class="info-row"><span>设备</span><span>{{ detailRow.device_id }}</span></div>
            <div class="info-row"><span>时间</span><span>{{ fmtTime(detailRow.created_at) }}</span></div>
            <div class="info-row"><span>缺陷</span><span>{{ names(detailRow.detections) }} ({{ detailRow.detections?.length || 0 }}处)</span></div>
            <div class="info-row"><span>置信度</span><span>{{ (detailRow.avg_confidence * 100).toFixed(0) }}%</span></div>
            <div class="info-row"><span>推理耗时</span><span>{{ detailRow.inference_ms?.toFixed(0) }}ms</span></div>
            <div class="info-row"><span>判定</span><span>{{ detailRow.decision === 'CLOUD' ? '云端复核' : '本地判定' }}</span></div>
            <div v-if="detailRow.agent_review?.reasoning" class="info-row info-review">
              <span>Agent复核</span>
              <span class="review-text">{{ detailRow.agent_review.reasoning }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fetchDefects } from '../api/client.js'

const CLASS_CN = {
  crazing: '裂纹', inclusion: '夹杂', patches: '斑块',
  pitted_surface: '麻点', rolled_in_scale: '氧化皮', scratches: '划痕',
  'rolled-in_scale': '氧化皮',
}
const CLASS_LIST = ['crazing', 'inclusion', 'patches', 'pitted_surface', 'rolled-in_scale', 'scratches']

const records = ref([])
const totalRecords = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 50
const lastUpdated = ref(null)
const detailRow = ref(null)
let poll = null

const filterType = ref('')
const filterDecision = ref('')
const filterReview = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(totalRecords.value / pageSize)))

const filteredRecords = computed(() => {
  return records.value.filter(r => {
    if (filterType.value) {
      const dets = r.detections || []
      if (!dets.some(d => d.class_name === filterType.value || d.class === filterType.value)) return false
    }
    if (filterDecision.value && r.decision !== filterDecision.value) return false
    if (filterReview.value === 'done' && !(r.agent_review?.reasoning && !r.agent_review.reasoning.startsWith('['))) return false
    if (filterReview.value === 'pending' && r.decision === 'CLOUD' && r.agent_review?.reasoning) return false
    return true
  })
})

const filteredCount = computed(() => filteredRecords.value.length)

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

async function refresh() {
  loading.value = true
  try {
    const res = await fetchDefects(pageSize, (page.value - 1) * pageSize)
    totalRecords.value = res.data.total
    records.value = res.data.items
    lastUpdated.value = new Date()
  } catch (e) { console.error('[Logs]', e) }
  loading.value = false
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  refresh()
}

function clearFilters() {
  filterType.value = ''
  filterDecision.value = ''
  filterReview.value = ''
}

function viewDetail(r) { detailRow.value = r }

function cnName(n) { return CLASS_CN[n] || n }
function names(d) { return d?.map(x => cnName(x.class_name || x.class)).join(', ') || '' }
function fmtTime(t) { return t ? new Date(t).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }
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
  if (text.includes('未配置')) return '未配置 API Key'
  if (text.includes('调用失败')) return 'Agent 调用失败'
  if (text.includes('无输出')) return 'Agent 未返回内容'
  if (text) return '复核完成'
  return '等待 Agent 复核中...'
}

onMounted(() => {
  refresh()
  poll = setInterval(refresh, 5000)
})
onUnmounted(() => clearInterval(poll))
</script>
