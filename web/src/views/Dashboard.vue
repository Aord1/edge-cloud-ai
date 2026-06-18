<template>
  <div class="page-container">
    <div class="page-header">
      <h2>缺陷统计仪表盘</h2>
      <div class="header-controls">
        <select v-model="hours" class="small-select" @change="refresh">
          <option :value="1">最近 1 小时</option>
          <option :value="6">最近 6 小时</option>
          <option :value="24">最近 24 小时</option>
          <option :value="72">最近 3 天</option>
          <option :value="168">最近 7 天</option>
        </select>
        <button class="btn-refresh" @click="refresh" :disabled="loading">🔄 刷新</button>
        <span v-if="lastUpdated" class="update-time">更新于 {{ fmtTime(lastUpdated) }}</span>
      </div>
    </div>

    <div v-if="loading && !stats" class="loading-box"><span class="spinner"></span> 加载中...</div>

    <template v-else-if="stats">
      <!-- 概览卡片 -->
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-label">总缺陷数</div>
        </div>
        <div class="stat-card card-edge">
          <div class="stat-value">{{ stats.edge_count }}</div>
          <div class="stat-label">本地判定</div>
        </div>
        <div class="stat-card card-cloud">
          <div class="stat-value">{{ stats.cloud_count }}</div>
          <div class="stat-label">云端复核</div>
        </div>
        <div class="stat-card card-ok">
          <div class="stat-value">{{ stats.reviewed_count }}</div>
          <div class="stat-label">已复核</div>
        </div>
        <div class="stat-card card-pending">
          <div class="stat-value">{{ stats.pending_count }}</div>
          <div class="stat-label">待复核</div>
        </div>
      </div>

      <!-- 图表区 -->
      <div class="chart-grid">
        <div class="chart-box">
          <div class="chart-title">缺陷类型分布</div>
          <div ref="typeChartEl" class="chart-canvas"></div>
        </div>
        <div class="chart-box">
          <div class="chart-title">置信度分布</div>
          <div ref="confChartEl" class="chart-canvas"></div>
        </div>
        <div class="chart-box chart-wide">
          <div class="chart-title">缺陷趋势</div>
          <div ref="trendChartEl" class="chart-canvas"></div>
        </div>
      </div>
    </template>

    <div v-else class="loading-box">暂无数据</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import * as echarts from 'echarts/core'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { fetchStats } from '../api/client.js'

echarts.use([PieChart, BarChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const CLASS_CN = {
  crazing: '裂纹', inclusion: '夹杂', patches: '斑块',
  pitted_surface: '麻点', rolled_in_scale: '氧化皮', scratches: '划痕',
  'rolled-in_scale': '氧化皮',
}

const hours = ref(24)
const stats = ref(null)
const loading = ref(false)
const lastUpdated = ref(null)

const typeChartEl = ref(null)
const confChartEl = ref(null)
const trendChartEl = ref(null)
let typeChart = null, confChart = null, trendChart = null
let poll = null

const darkTheme = {
  backgroundColor: 'transparent',
  textStyle: { color: '#94a3b8' },
  title: { textStyle: { color: '#e2e8f0' } },
}

async function refresh() {
  loading.value = true
  try {
    const r = await fetchStats(hours.value)
    stats.value = r.data
    lastUpdated.value = new Date()
    await nextTick()
    renderCharts()
  } catch (e) {
    console.error('[Dashboard]', e)
  }
  loading.value = false
}

function renderCharts() {
  if (!stats.value) return
  renderTypeChart()
  renderConfChart()
  renderTrendChart()
}

function renderTypeChart() {
  if (!typeChartEl.value) return
  if (!typeChart) typeChart = echarts.init(typeChartEl.value)
  const data = stats.value.type_distribution.map(t => ({
    name: CLASS_CN[t.class_name] || t.class_name,
    value: t.count,
  }))
  typeChart.setOption({
    ...darkTheme,
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: 0, textStyle: { color: '#94a3b8' } },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
      itemStyle: { borderColor: '#1a2332', borderWidth: 2 },
      label: { color: '#e2e8f0' },
      data,
    }],
    color: ['#3b82f6', '#ef4444', '#f59e0b', '#22c55e', '#8b5cf6', '#06b6d4'],
  })
}

function renderConfChart() {
  if (!confChartEl.value) return
  if (!confChart) confChart = echarts.init(confChartEl.value)
  const labels = ['0-20%', '20-40%', '40-60%', '60-80%', '80-100%']
  confChart.setOption({
    ...darkTheme,
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: labels, axisLine: { lineStyle: { color: '#1e2d40' } } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#1e2d40' } }, splitLine: { lineStyle: { color: '#1e2d40' } } },
    series: [{
      type: 'bar', data: stats.value.confidence_buckets,
      itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
      barWidth: '60%',
    }],
  })
}

function renderTrendChart() {
  if (!trendChartEl.value) return
  if (!trendChart) trendChart = echarts.init(trendChartEl.value)
  const t = stats.value.trend
  trendChart.setOption({
    ...darkTheme,
    tooltip: { trigger: 'axis' },
    legend: { data: ['本地', '云端'], top: 0, textStyle: { color: '#94a3b8' } },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: t.map(p => p.time), axisLine: { lineStyle: { color: '#1e2d40' } } },
    yAxis: { type: 'value', axisLine: { lineStyle: { color: '#1e2d40' } }, splitLine: { lineStyle: { color: '#1e2d40' } } },
    series: [
      { name: '本地', type: 'line', data: t.map(p => p.edge), smooth: true, itemStyle: { color: '#22c55e' }, areaStyle: { opacity: 0.1 } },
      { name: '云端', type: 'line', data: t.map(p => p.cloud), smooth: true, itemStyle: { color: '#ef4444' }, areaStyle: { opacity: 0.1 } },
    ],
  })
}

function fmtTime(t) { return t ? new Date(t).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '' }

function handleResize() {
  typeChart?.resize()
  confChart?.resize()
  trendChart?.resize()
}

onMounted(() => {
  refresh()
  poll = setInterval(refresh, 10000)
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  clearInterval(poll)
  window.removeEventListener('resize', handleResize)
  typeChart?.dispose()
  confChart?.dispose()
  trendChart?.dispose()
})

watch(hours, () => refresh())
</script>
