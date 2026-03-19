<template>
  <div class="evidence-container">
    <el-card class="box-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>创建取证任务</span>
        </div>
      </template>
      
      <!-- 取证表单 -->
      <el-form :model="form" label-width="120px" :inline="false">
        <el-form-item label="目标 CID" required>
          <!-- ★ 改动1：CID输入框后面加网关直达 -->
          <div style="display: flex; align-items: center; width: 100%; gap: 8px;">
            <el-input v-model="form.cid" placeholder="请输入可疑的 IPFS CID" clearable style="flex: 1;">
              <template #prepend>ipfs://</template>
            </el-input>
            <GatewayLink v-if="form.cid" :cid="form.cid" />
          </div>
        </el-form-item>
        <el-row>
          <el-col :span="12">
            <el-form-item label="案件编号">
              <el-input v-model="form.case_id" placeholder="如：CASE-2024-001" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="取证人员 ID">
              <el-input v-model="form.investigator_id" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="submitTask" :icon="loading ? undefined : Search">
            {{ loading ? '取证中...' : '启动取证固化' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ================= 运行日志终端区 ================= -->
    <el-card v-if="showTerminal" shadow="never" class="terminal-card">
      <div class="terminal-header">
        <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
        <span class="title">取证日志 (Forensics Log)</span>
      </div>
      <div class="terminal-box" ref="terminalRef">
        <div v-for="(log, idx) in executionLogs" :key="idx" :class="['log-line', log.type]">
          <span class="time">[{{ log.time }}]</span> 
          <span class="content">> {{ log.text }}</span>
        </div>
        <div v-if="loading" class="cursor-blink">_</div>
      </div>
    </el-card>

    <!-- ================= 结果展示区 (自动弹出) ================= -->
    <transition name="el-fade-in-linear">
      <div v-if="result && !loading" class="result-area">
        
        <!-- 顶部全局成功提示 -->
        <el-alert 
          title="取证与固化流水线执行完毕！数据已安全上链入库。" 
          type="success" 
          show-icon 
          :closable="false"
          style="margin-bottom: 20px;" 
        />

        <!-- 中部左右分栏：技术概览与时间线 -->
        <el-row :gutter="20">
          <el-col :span="14">
            <el-card shadow="never" class="result-card">
              <template #header>
                <div class="card-header">
                  <span>司法证据哈希值 (三重校验)</span>
                  <!-- ★ 改动2：结果区标题旁加网关直达 -->
                  <GatewayLink :cid="form.cid" />
                </div>
              </template>
              <el-descriptions :column="1" border>
                <el-descriptions-item label="文件大小 (Bytes)">
                  <el-tag type="info">{{ result.report_data.evidence_summary.file_size_bytes }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="文件类型/审查">
                  <el-tag :type="result.report_data.analysis_results.is_illegal ? 'danger' : 'success'">
                    {{ result.report_data.analysis_results.file_type }}
                  </el-tag>
                  <el-tag v-if="result.report_data.analysis_results.is_illegal" type="danger" effect="dark" style="margin-left: 10px;">
                    ⚠️ 异常: {{ result.report_data.analysis_results.matched_keywords.join(', ') }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="提取文本/摘要">
                  <div class="text-summary-box">
                    {{ result.report_data.analysis_results.extracted_text || '无可用文本' }}
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="SHA-256 (国标)">
                  <span class="hash-text">{{ result.report_data.evidence_summary.hash_values.sha256 }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="SHA-512 (高强)">
                  <span class="hash-text">{{ result.report_data.evidence_summary.hash_values.sha512 }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="Keccak-256">
                  <span class="hash-text chain-hash">{{ result.report_data.evidence_summary.hash_values.keccak256 }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="Merkle Root">
                  <el-tag type="success" size="large" class="merkle-tag">{{ result.merkle_root }}</el-tag>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-col>

          <el-col :span="10">
            <el-card shadow="never" class="result-card">
              <template #header><div class="card-header"><span>监管链 (Chain of Custody)</span></div></template>
              <el-timeline>
                <el-timeline-item
                  v-for="(record, index) in result.report_data.chain_of_custody"
                  :key="index"
                  :timestamp="formatTime(record.timestamp)"
                  :type="index === result.report_data.chain_of_custody.length - 1 ? 'success' : 'primary'"
                  placement="top"
                >
                  <el-card shadow="hover" class="timeline-card">
                    <h4 style="margin: 0 0 8px 0; color: #303133;">操作: {{ record.action }}</h4>
                    <p class="timeline-p"><strong>操作人:</strong> {{ record.operator }}</p>
                    <p class="timeline-p details-text"><strong>审计:</strong> {{ record.record_hash.substring(0, 16) }}...</p>
                  </el-card>
                </el-timeline-item>
              </el-timeline>
            </el-card>
          </el-col>
        </el-row>

        <!-- 分割线与报告 -->
        <el-divider content-position="center" style="margin: 40px 0;">
          <el-icon size="18" style="vertical-align: middle; margin-right: 5px;"><DocumentChecked /></el-icon>
          <span style="font-size: 18px; font-weight: bold; color: #606266;">法定电子数据取证报告</span>
        </el-divider>

        <div class="report-display-area">
          <ForensicReport :reportData="result.report_data" />
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, DocumentChecked } from '@element-plus/icons-vue' 
import { evidenceApi, type CollectParams } from '../api/index'
import ForensicReport from '../components/ForensicReport.vue'
import GatewayLink from '../components/GatewayLink.vue'  // ★ 改动3：导入组件

const route = useRoute()
const loading = ref(false)
const result = ref<any>(null)

const form = reactive<CollectParams>({
  cid: '', 
  case_id: '',
  investigator_id: 'Police_001_Sys'
})

// === 终端日志相关状态 ===
const showTerminal = ref(false)
const terminalRef = ref<HTMLElement | null>(null)
const executionLogs = ref<{time: string, text: string, type: string}[]>([])
let timers: any[] = []

// 添加单条日志
const pushLog = (text: string, type = 'info') => {
  const now = new Date()
  const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}.${String(now.getMilliseconds()).padStart(3,'0')}`
  executionLogs.value.push({ time: timeStr, text, type })
  nextTick(() => {
    if (terminalRef.value) {
      terminalRef.value.scrollTop = terminalRef.value.scrollHeight
    }
  })
}

// 清除所有定时器
const clearTimers = () => {
  timers.forEach(clearTimeout)
  timers = []
}

const generateCaseId = async () => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const datePrefix = `CASE-${year}-${month}-${day}`

  try {
    const historyList = await evidenceApi.getHistory()
    const todaysCases = historyList.filter((item: any) => item.case_id && item.case_id.startsWith(datePrefix))
    
    let nextNumber = 1
    if (todaysCases.length > 0) {
      const maxNumber = Math.max(...todaysCases.map((item: any) => {
        const parts = item.case_id.split('-')
        const num = parseInt(parts[parts.length - 1], 10)
        return isNaN(num) ? 0 : num
      }))
      nextNumber = maxNumber + 1
    }
    form.case_id = `${datePrefix}-${String(nextNumber).padStart(3, '0')}`
  } catch (error) {
    form.case_id = `${datePrefix}-001`
  }
}

onMounted(() => {
  generateCaseId()
  if (route.query.target_cid) {
    form.cid = route.query.target_cid as string
  }
})

// 提交任务核心方法
const submitTask = async () => {
  if (!form.cid) {
    ElMessage.warning('请输入目标 CID')
    return
  }
  
  loading.value = true
  result.value = null 
  showTerminal.value = true
  executionLogs.value = []
  clearTimers()
  
  pushLog(`[1/5] 初始化取证沙箱，案件流水号分配: ${form.case_id}`, 'info')
  timers.push(setTimeout(() => pushLog(`锁定目标 CID: ${form.cid}`, 'warning'), 600))
  timers.push(setTimeout(() => pushLog('启动 GatewayMonitor，加载防阻断网关代理配置...', 'info'), 1200))
  timers.push(setTimeout(() => pushLog('向 IPFS DHT 网络广播 FindProvs 寻址请求...', 'info'), 2000))
  timers.push(setTimeout(() => pushLog('正在尝试建立数据传输隧道 (Downloading)...', 'warning'), 3500))

  try {
    const res = await evidenceApi.collect(form)
    clearTimers()
    
    pushLog(`[2/5] 物理文件拉取成功！开始流式计算三重哈希...`, 'success')
    pushLog(`SHA-256 / SHA-512 / Keccak-256 校验完毕。`, 'info')
    
    timers.push(setTimeout(() => pushLog(`[3/5] 触发 ContentAnalyzer，识别多媒体文件特征...`, 'info'), 500))
    
    const isIllegal = res.report_data.analysis_results.is_illegal
    if (isIllegal) {
       timers.push(setTimeout(() => pushLog(`[⚠️ 警告] Tesseract OCR 命中特征字典: ${res.report_data.analysis_results.matched_keywords.join(',')}`, 'danger'), 1200))
    } else {
       timers.push(setTimeout(() => pushLog(`NLP 分析完毕，未发现明显违规涉案词汇。`, 'success'), 1200))
    }

    timers.push(setTimeout(() => pushLog(`[4/5] 封装 Merkle Tree 证据块，记录监管链 (Chain of Custody)...`, 'warning'), 1800))
    timers.push(setTimeout(() => pushLog(`[5/5] 数据持久化入库完成！生成最终司法文书。`, 'success'), 2500))

    timers.push(setTimeout(() => {
      result.value = res
      loading.value = false
      ElMessage.success('取证固化全部完成！')
    }, 3200))

  } catch (error: any) {
    clearTimers()
    pushLog(`[ERROR] 任务中断: ${error.response?.data?.detail || '网络连接超时或文件不存在'}`, 'danger')
    loading.value = false
  }
}

const formatTime = (isoString: string) => {
  return new Date(isoString).toLocaleString()
}
</script>

<style scoped>
.evidence-container { display: flex; flex-direction: column; gap: 20px; }
.card-header { font-weight: bold; font-size: 16px; display: flex; align-items: center; justify-content: space-between; }

/* 模拟 Mac 风格控制台 */
.terminal-card {
  margin-top: 10px;
  background-color: #1e1e1e;
  border: 1px solid #333;
  border-radius: 6px;
}
.terminal-header {
  background: #333;
  padding: 8px 15px;
  display: flex;
  align-items: center;
  border-top-left-radius: 6px;
  border-top-right-radius: 6px;
  margin: -20px -20px 10px -20px;
}
.dot { width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
.dot.red { background: #ff5f56; }
.dot.yellow { background: #ffbd2e; }
.dot.green { background: #27c93f; }
.terminal-header .title {
  color: #a9b7c6; font-size: 12px; margin-left: 10px; font-family: monospace;
}

.terminal-box {
  background-color: #1e1e1e;
  color: #a9b7c6;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 13px;
  height: 200px;
  overflow-y: auto;
  line-height: 1.6;
}
.log-line { margin-bottom: 4px; }
.log-line .time { color: #888; margin-right: 8px; }
.log-line.info { color: #4CAF50; }
.log-line.warning { color: #FFC107; }
.log-line.danger { color: #ff5f56; font-weight: bold; }
.log-line.success { color: #00BCD4; font-weight: bold; }

.cursor-blink { display: inline-block; animation: blink 1s step-end infinite; color: #fff; margin-top: 5px;}
@keyframes blink { 50% { opacity: 0; } }

/* 结果区样式 */
.result-area { margin-top: 10px; }
.result-card { height: 100%; }
.text-summary-box { max-height: 80px; overflow-y: auto; color: #606266; font-size: 13px; line-height: 1.5; background-color: #f5f7fa; padding: 8px; border-radius: 4px; }
.hash-text { font-family: 'Courier New', Courier, monospace; word-break: break-all; font-size: 13px; color: #606266; }
.chain-hash { color: #E6A23C; }
.merkle-tag { font-family: 'Courier New', Courier, monospace; font-weight: bold; letter-spacing: 1px; }
.timeline-card { padding: 5px; }
.timeline-p { margin: 4px 0; font-size: 13px; color: #606266; }
.details-text { color: #909399; font-family: monospace; }
.report-display-area { background-color: #dcdfe6; padding: 30px; border-radius: 8px; box-shadow: inset 0 2px 12px 0 rgba(0, 0, 0, 0.1); }
</style>