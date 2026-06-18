<template>
  <div class="page-container">
    <div class="page-header">
      <h2>系统状态监控</h2>
      <div class="header-controls">
        <button class="btn-refresh" @click="refreshAll" :disabled="loading">🔄 刷新</button>
        <span v-if="lastUpdated" class="update-time">更新于 {{ fmtTime(lastUpdated) }}</span>
      </div>
    </div>

    <div v-if="loading && !sysStatus" class="loading-box"><span class="spinner"></span> 加载中...</div>

    <template v-else>
      <!-- 概览卡片 -->
      <div class="stat-cards">
        <div class="stat-card" :class="edgeOk ? 'card-ok' : 'card-pending'">
          <div class="stat-value">{{ edgeOk ? '在线' : '离线' }}</div>
          <div class="stat-label">边缘端</div>
        </div>
        <div class="stat-card" :class="cloudOk ? 'card-ok' : 'card-pending'">
          <div class="stat-value">{{ cloudOk ? '在线' : '离线' }}</div>
          <div class="stat-label">云端</div>
        </div>
        <div class="stat-card" :class="dbOk ? 'card-ok' : 'card-pending'">
          <div class="stat-value">{{ dbOk ? '正常' : '异常' }}</div>
          <div class="stat-label">数据库</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ sysStatus?.database.total_records || 0 }}</div>
          <div class="stat-label">总记录数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ sysStatus?.database.recent_1h || 0 }}</div>
          <div class="stat-label">近1小时</div>
        </div>
      </div>

      <!-- 边缘端指标 -->
      <div class="status-section">
        <div class="section-title">边缘端运行指标</div>
        <div v-if="edgeStatus" class="metric-grid">
          <div class="metric-item">
            <span class="metric-label">检测状态</span>
            <span class="metric-value" :class="edgeStatus.state === 'running' ? 'val-ok' : 'val-muted'">{{ edgeStatus.state }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">推理帧率</span>
            <span class="metric-value">{{ edgeStatus.fps || 0 }} FPS</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">推理耗时</span>
            <span class="metric-value">{{ edgeStatus.inference_ms?.toFixed(0) || 0 }} ms</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">当前缺陷数</span>
            <span class="metric-value">{{ edgeStatus.count || 0 }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">当前决策</span>
            <span class="metric-value" :class="edgeStatus.decision === 'CLOUD' ? 'val-warn' : 'val-ok'">{{ edgeStatus.decision || '—' }}</span>
          </div>
        </div>
        <div v-else class="metric-empty">边缘端离线，无法获取指标</div>
      </div>

      <!-- 云端指标 -->
      <div v-if="sysStatus" class="status-section">
        <div class="section-title">云端运行指标</div>
        <div class="metric-grid">
          <div class="metric-item">
            <span class="metric-label">主机名</span>
            <span class="metric-value">{{ sysStatus.cloud.host }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">平台</span>
            <span class="metric-value">{{ sysStatus.cloud.platform }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">运行时长</span>
            <span class="metric-value">{{ fmtUptime(sysStatus.cloud.uptime_sec) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">CPU 使用率</span>
            <span class="metric-value" :class="sysStatus.cloud.cpu_percent > 80 ? 'val-warn' : 'val-ok'">{{ sysStatus.cloud.cpu_percent }}%</span>
            <span class="metric-sub">{{ sysStatus.cloud.cpu_cores }} 核</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">内存使用</span>
            <span class="metric-value">{{ sysStatus.cloud.mem_used_mb }} / {{ sysStatus.cloud.mem_total_mb }} MB</span>
            <span class="metric-sub" :class="sysStatus.cloud.mem_percent > 80 ? 'val-warn' : ''">{{ sysStatus.cloud.mem_percent }}%</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">磁盘使用</span>
            <span class="metric-value">{{ sysStatus.cloud.disk_used_gb }} / {{ sysStatus.cloud.disk_total_gb }} GB</span>
            <span class="metric-sub" :class="sysStatus.cloud.disk_percent > 80 ? 'val-warn' : ''">{{ sysStatus.cloud.disk_percent }}%</span>
          </div>
        </div>
      </div>

      <!-- 数据库指标 -->
      <div v-if="sysStatus" class="status-section">
        <div class="section-title">数据库指标</div>
        <div class="metric-grid">
          <div class="metric-item">
            <span class="metric-label">地址</span>
            <span class="metric-value">{{ sysStatus.database.host }}:{{ sysStatus.database.port }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">数据库</span>
            <span class="metric-value">{{ sysStatus.database.name }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">总记录数</span>
            <span class="metric-value">{{ sysStatus.database.total_records }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">近1小时新增</span>
            <span class="metric-value">{{ sysStatus.database.recent_1h }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { fetchSystemStatus, edgeStatus } from '../api/client.js'

const sysStatus = ref(null)
const edgeStatusData = ref(null)
const loading = ref(false)
const lastUpdated = ref(null)
const edgeOk = ref(false)
const cloudOk = ref(false)
const dbOk = ref(false)
let poll = null

async function refreshAll() {
  loading.value = true
  try {
    const r = await fetchSystemStatus()
    sysStatus.value = r.data
    cloudOk.value = true
    dbOk.value = true
  } catch { cloudOk.value = false; dbOk.value = false }

  try {
    const er = await edgeStatus()
    edgeStatusData.value = er
    edgeOk.value = true
  } catch { edgeOk.value = false; edgeStatusData.value = null }

  lastUpdated.value = new Date()
  loading.value = false
}

function fmtTime(t) { return t ? new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }
function fmtUptime(sec) {
  if (!sec) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

onMounted(() => {
  refreshAll()
  poll = setInterval(refreshAll, 5000)
})
onUnmounted(() => clearInterval(poll))
</script>
