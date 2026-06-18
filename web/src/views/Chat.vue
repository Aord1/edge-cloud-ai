<template>
  <div class="page-container chat-page">
    <div class="page-header">
      <h2>AI 复核对话</h2>
      <span class="chat-hint">输入问题，Agent 会查询缺陷记录和质检标准后回答</span>
    </div>

    <div class="chat-body">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="msgBox">
        <div v-if="!messages.length" class="chat-empty">
          <div class="placeholder-icon">🤖</div>
          <div>开始与 AI Agent 对话</div>
          <div class="chat-suggestions">
            <button class="suggestion-btn" @click="send('今天有哪些缺陷需要复核？')">今天有哪些缺陷需要复核？</button>
            <button class="suggestion-btn" @click="send('裂纹缺陷的判定标准是什么？')">裂纹缺陷的判定标准是什么？</button>
            <button class="suggestion-btn" @click="send('统计最近24小时的缺陷分布')">统计最近24小时的缺陷分布</button>
          </div>
        </div>

        <div v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role">
          <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="msg-content">
            <div v-if="msg.toolCalls.length" class="msg-tools">
              <div v-for="(tc, j) in msg.toolCalls" :key="j" class="tool-line">
                <span class="tool-icon">🔧</span>
                <span class="tool-name">{{ tc.name }}</span>
                <span class="tool-input">{{ tc.input }}</span>
              </div>
            </div>
            <div v-if="msg.toolResults.length" class="msg-tool-results">
              <details v-for="(tr, j) in msg.toolResults" :key="j">
                <summary>工具结果 #{{ j + 1 }}</summary>
                <pre>{{ tr }}</pre>
              </details>
            </div>
            <div class="msg-text" v-if="msg.text">{{ msg.text }}</div>
            <div v-if="msg.streaming" class="streaming-dot"><span class="spinner"></span></div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-area">
        <textarea
          v-model="input" class="chat-input" rows="2"
          placeholder="输入消息... (Ctrl+Enter 发送)"
          @keydown.ctrl.enter="send(input)"
          :disabled="streaming"
        ></textarea>
        <button class="btn-send" @click="send(input)" :disabled="streaming || !input.trim()">
          {{ streaming ? '推理中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onUnmounted } from 'vue'
import { chatStream } from '../api/client.js'

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const msgBox = ref(null)

async function send(text) {
  const trimmed = text.trim()
  if (!trimmed || streaming.value) return

  messages.value.push({ role: 'user', text: trimmed, toolCalls: [], toolResults: [], streaming: false })
  input.value = ''
  await scrollToBottom()

  const agentMsg = { role: 'agent', text: '', toolCalls: [], toolResults: [], streaming: true }
  messages.value.push(agentMsg)
  streaming.value = true

  try {
    await chatStream(trimmed, 'chat-page', (event) => {
      if (event.type === 'text' && event.content) {
        agentMsg.text += event.content
      } else if (event.type === 'tool_call') {
        agentMsg.toolCalls.push({
          name: event.tool_name,
          input: JSON.stringify(event.tool_input).slice(0, 100),
        })
      } else if (event.type === 'tool_result') {
        agentMsg.toolResults.push(event.content.slice(0, 500))
      } else if (event.type === 'done') {
        agentMsg.streaming = false
      }
      scrollToBottom()
    })
  } catch (e) {
    agentMsg.text = '对话失败: ' + e.message
    agentMsg.streaming = false
  }
  streaming.value = false
}

async function scrollToBottom() {
  await nextTick()
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}
</script>
