<template>
  <div class="app-layout">
    <nav class="nav-bar">
      <router-link to="/" class="nav-brand">边云协同检测</router-link>
      <div class="nav-links">
        <router-link to="/" class="nav-link" exact-active-class="active">实时监控</router-link>
        <router-link to="/dashboard" class="nav-link" active-class="active">统计仪表盘</router-link>
        <router-link to="/logs" class="nav-link" active-class="active">质检日志</router-link>
        <router-link to="/chat" class="nav-link" active-class="active">AI 对话</router-link>
        <router-link to="/system" class="nav-link" active-class="active">系统状态</router-link>
      </div>
    </nav>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
</script>
