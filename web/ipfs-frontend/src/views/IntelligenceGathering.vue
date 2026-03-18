<template>
  <div class="gather-container">
    <el-row :gutter="20">
      
      <!-- 左侧：控制台与扫描雷达 -->
      <el-col :span="8">
        <el-card shadow="hover" class="control-card">
          <template #header><div class="card-header"><span>多源嗅探控制台</span></div></template>
          
          <div class="control-panel">
            <el-input v-model="scanKeyword" placeholder="输入涉案关键字 (如: 诈骗, 赌博)" class="mb-3">
              <template #prepend>监控词</template>
            </el-input>
            
            <div class="source-checkboxes mb-3">
              <el-checkbox v-model="sources.dht" disabled checked>IPFS DHT网络</el-checkbox>
              <el-checkbox v-model="sources.tg" disabled checked>Telegram群组</el-checkbox>
              <el-checkbox v-model="sources.dark" disabled checked>暗网/洋葱路由</el-checkbox>
            </div>

            <!-- 核心按钮：切换雷达状态 -->
            <el-button 
              :type="isMonitoring ? 'danger' : 'primary'" 
              @click="toggleMonitor" 
              class="scan-btn" 
              :icon="isMonitoring ? 'Loading' : 'Aim'"
            >
              {{ isMonitoring ? '🔴 停止实时监控' : '🟢 开启实时情报雷达' }}
            </el-button>
          </div>

          <!-- 模拟黑客风的日志终端 -->
          <div class="terminal-box" ref="terminalRef">
            <div v-for="(log, idx) in scanLogs" :key="idx" :class="log.type">
              <span class="time-prefix">[{{ log.time }}]</span> > {{ log.text }}
            </div>
            <div v-if="isMonitoring" class="cursor-blink">_</div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：发现的线索池 (Clue Pool) -->
      <el-col :span="16">
        <el-card shadow="never" class="table-card">
          <template #header>
            <div class="card-header">
              <span>全网情报线索池 (Clue Pool)</span>
              <el-button type="primary" size="small" plain @click="fetchClues" icon="Refresh">刷新线索</el-button>
            </div>
          </template>

          <el-table :data="clueList" border stripe height="calc(100vh - 220px)" v-loading="tableLoading">
            <el-table-column prop="discovered_at" label="发现时间" width="160">
              <template #default="scope">{{ formatTime(scope.row.discovered_at) }}</template>
            </el-table-column>
            
            <el-table-column prop="source" label="发现渠道" width="180">
              <template #default="scope">
                <el-tag v-if="scope.row.source.includes('DHT')" type="success" size="small">{{ scope.row.source }}</el-tag>
                <el-tag v-else-if="scope.row.source.includes('Reddit')" type="primary" size="small">公开论坛(Reddit)</el-tag>
                <el-tag v-else type="info" size="small">{{ scope.row.source }}</el-tag>
              </template>
            </el-table-column>

            <el-table-column prop="cid" label="可疑 CID" show-overflow-tooltip>
              <template #default="scope">
                <span class="cid-text">{{ scope.row.cid }}</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="120" fixed="right" align="center">
              <template #default="scope">
                <el-button type="warning" size="small" icon="Promotion" @click="dispatchForensics(scope.row.cid)">
                  下发取证
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { clueApi } from '../api/index'
import { ElMessage } from 'element-plus'

const router = useRouter()
const scanKeyword = ref('') // 默认给点关键字
const isMonitoring = ref(false)
const tableLoading = ref(false)
const clueList = ref<any[]>([])
const sources = ref({ dht: true, tg: true, dark: true })

let monitorInterval: ReturnType<typeof setInterval> | null = null

// 终端日志
const terminalRef = ref<HTMLElement | null>(null)
const scanLogs = ref<{time: string, text: string, type: string}[]>([])

// 记录日志并自动滚动
const pushLog = (text: string, type = "info") => {
  const now = new Date()
  const timeStr = now.toLocaleTimeString()
  scanLogs.value.push({ time: timeStr, text, type })
  
  nextTick(() => {
    if (terminalRef.value) {
      terminalRef.value.scrollTop = terminalRef.value.scrollHeight
    }
  })
}

// 获取线索列表
const fetchClues = async () => {
  tableLoading.value = true
  try {
    const res = await clueApi.getClues()
    clueList.value = res
  } catch (error) {
    ElMessage.error('获取线索失败')
  } finally {
    tableLoading.value = false
  }
}

// 核心：单次执行扫描逻辑
const performScan = async () => {
  pushLog(`[雷达扫描] 正在请求外网 API 及本地节点...`, "info")
  try {
    // 将字符串按逗号分割转为数组传给后端
    const keywordsArray = scanKeyword.value ? scanKeyword.value.split(',').map(s => s.trim()) : []
    const res = await clueApi.triggerScan(keywordsArray)
    
    if (res.length > 0) {
      pushLog(`🚨 发现新线索！捕获到 ${res.length} 个可疑 CID！`, "danger")
      await fetchClues() // 刷新表格
    } else {
      pushLog(`网络安静，未发现新威胁。`, "success")
    }
  } catch (error) {
    pushLog("请求异常，跳过本轮扫描。", "warning")
  }
}

// 核心：实时监控开关
const toggleMonitor = () => {
  if (isMonitoring.value) {
    // 停止监控
    isMonitoring.value = false
    if (monitorInterval) clearInterval(monitorInterval)
    pushLog("🔴 实时嗅探雷达已关闭。", "warning")
  } else {
    // 启动监控
    isMonitoring.value = true
    pushLog("🟢 启动实时多源嗅探雷达...", "success")
    pushLog("监听 IPFS Swarm P2P 流量中...", "info")
    
    // 立即执行一次，然后每 8 秒执行一次轮询
    performScan()
    monitorInterval = setInterval(performScan, 8000)
  }
}

// 核心枢纽：携参跳转到取证页面
const dispatchForensics = (cid: string) => {
  ElMessage.success('已下发取证任务，正在跳转...')
  router.push({ path: '/evidence', query: { target_cid: cid } })
}

// 格式化中国时间
const formatTime = (isoString: string) => {
  if(!isoString) return ''
  return new Date(isoString).toLocaleString()
}

// 生命周期钩子
onMounted(() => {
  pushLog("系统初始化完毕。等待开启雷达...", "info")
  fetchClues()
})

onBeforeUnmount(() => {
  // 组件销毁时必须清除定时器，防止内存泄漏和后台无效请求
  if (monitorInterval) clearInterval(monitorInterval)
})
</script>

<style scoped>
.gather-container { padding: 10px 0; }
.card-header { font-weight: bold; }
.mb-3 { margin-bottom: 15px; }
.scan-btn { width: 100%; height: 40px; font-weight: bold; letter-spacing: 1px; }

/* 黑客风终端 */
.terminal-box {
  background-color: #1e1e1e;
  color: #a9b7c6;
  font-family: 'Consolas', monospace;
  font-size: 13px;
  padding: 15px;
  border-radius: 4px;
  height: 250px;
  overflow-y: auto;
  margin-top: 20px;
  box-shadow: inset 0 0 10px rgba(0,0,0,0.8);
  line-height: 1.5;
}
.terminal-box .time-prefix { color: #888; margin-right: 5px; }
.terminal-box .info { color: #4CAF50; margin-bottom: 4px; }
.terminal-box .warning { color: #FFC107; margin-bottom: 4px; }
.terminal-box .danger { color: #ff5f56; font-weight: bold; margin-bottom: 4px; }
.terminal-box .success { color: #00BCD4; font-weight: bold; margin-bottom: 4px; }
.cursor-blink { display: inline-block; animation: blink 1s step-end infinite; color: #fff; margin-top: 5px; }
@keyframes blink { 50% { opacity: 0; } }

.cid-text { font-family: monospace; color: #606266; font-size: 13px; }
</style>