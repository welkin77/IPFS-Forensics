<template>
  <div class="gather-container">
    <el-row :gutter="20">
      
      <!-- 左侧：控制台与扫描雷达 - 完全不变 -->
      <el-col :span="8">
        <el-card shadow="hover" class="control-card">
          <template #header><div class="card-header"><span>多源嗅探控制台</span></div></template>
          
          <div class="control-panel">
            <el-input v-model="radarStore.scanKeyword" placeholder="输入涉案关键字 (如: 诈骗, 赌博)" class="mb-3">
              <template #prepend>监控词</template>
            </el-input>
            
            <div class="source-checkboxes mb-3">
              <el-checkbox v-model="sources.dht" disabled checked>IPFS DHT网络</el-checkbox>
              <el-checkbox v-model="sources.tg" disabled checked>Telegram群组</el-checkbox>
              <el-checkbox v-model="sources.dark" disabled checked>暗网/洋葱路由</el-checkbox>
            </div>

            <el-button 
              :type="radarStore.isMonitoring ? 'danger' : 'primary'" 
              @click="radarStore.toggleMonitor()" 
              class="scan-btn" 
              :icon="radarStore.isMonitoring ? 'Loading' : 'Aim'"
            >
              {{ radarStore.isMonitoring ? '🔴 停止实时监控' : '🟢 开启实时情报雷达' }}
            </el-button>
          </div>

          <div class="terminal-box" ref="terminalRef">
            <div v-for="(log, idx) in radarStore.scanLogs" :key="idx" :class="log.type">
              <span class="time-prefix">[{{ log.time }}]</span> > {{ log.text }}
            </div>
            <div v-if="radarStore.isMonitoring" class="cursor-blink">_</div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：线索池 -->
      <el-col :span="16">
        <el-card shadow="never" class="table-card">
          <template #header>
            <div class="card-header">
              <span>全网情报线索池 (Clue Pool)</span>
              <el-button type="primary" size="small" plain @click="radarStore.fetchClues()" icon="Refresh">刷新线索</el-button>
            </div>
          </template>

          <el-table :data="radarStore.clueList" border stripe height="calc(100vh - 220px)" v-loading="radarStore.tableLoading">
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

            <!-- ★ 改动：操作列加宽，加入网关直达按钮 -->
            <el-table-column label="操作" width="200" fixed="right" align="center">
              <template #default="scope">
                <GatewayLink :cid="scope.row.cid" />
                <el-button type="warning" size="small" icon="Promotion" @click="dispatchForensics(scope.row.cid)" style="margin-left: 6px;">
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
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useRadarStore } from '../stores/radar'
import GatewayLink from '../components/GatewayLink.vue'  // ★ 新增

const radarStore = useRadarStore()
const router = useRouter()
const sources = ref({ dht: true, tg: true, dark: true })
const terminalRef = ref<HTMLElement | null>(null)

watch(
  () => radarStore.scanLogs.length,
  () => {
    nextTick(() => {
      if (terminalRef.value) {
        terminalRef.value.scrollTop = terminalRef.value.scrollHeight
      }
    })
  }
)

const dispatchForensics = (cid: string) => {
  ElMessage.success('已下发取证任务，正在跳转...')
  router.push({ path: '/evidence', query: { target_cid: cid } })
}

const formatTime = (isoString: string) => {
  if (!isoString) return ''
  return new Date(isoString).toLocaleString()
}

onMounted(() => {
  if (radarStore.clueList.length === 0) {
    radarStore.fetchClues()
  }
  if (radarStore.scanLogs.length === 0) {
    radarStore.pushLog('系统初始化完毕。等待开启雷达...', 'info')
  }
})
</script>

<style scoped>
.gather-container { padding: 10px 0; }
.card-header { font-weight: bold; }
.mb-3 { margin-bottom: 15px; }
.scan-btn { width: 100%; height: 40px; font-weight: bold; letter-spacing: 1px; }

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