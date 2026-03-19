import { defineStore } from 'pinia'
import { ref } from 'vue'
import { clueApi } from '../api/index'

export interface ScanLog {
  time: string
  text: string
  type: string
}

export const useRadarStore = defineStore('radar', () => {
  // ========== 状态 ==========
  const isMonitoring = ref(false)
  const scanLogs = ref<ScanLog[]>([])
  const clueList = ref<any[]>([])
  const tableLoading = ref(false)
  const scanKeyword = ref('')

  let monitorInterval: ReturnType<typeof setInterval> | null = null

  // ========== 日志 ==========
  function pushLog(text: string, type = 'info') {
    const now = new Date()
    scanLogs.value.push({
      time: now.toLocaleTimeString(),
      text,
      type
    })
    if (scanLogs.value.length > 500) {
      scanLogs.value = scanLogs.value.slice(-300)
    }
  }

  // ========== 获取线索 ==========
  async function fetchClues() {
    tableLoading.value = true
    try {
      const res = await clueApi.getClues()
      // res 可能是 axios response 或直接数据，兼容两种情况
      clueList.value = Array.isArray(res) ? res : (res as any)?.data ?? []
    } catch {
      // 后台运行时静默失败
    } finally {
      tableLoading.value = false
    }
  }

  // ========== 单次扫描 ==========
  async function performScan() {
    pushLog('[雷达扫描] 正在请求外网 API 及本地节点...', 'info')
    try {
      const keywordsArray = scanKeyword.value
        ? scanKeyword.value.split(',').map(s => s.trim())
        : []
      const res = await clueApi.triggerScan(keywordsArray)
      // 同样兼容两种返回格式
      const data = Array.isArray(res) ? res : (res as any)?.data ?? []

      if (data.length > 0) {
        pushLog(`🚨 发现新线索！捕获到 ${data.length} 个可疑 CID！`, 'danger')
        await fetchClues()
      } else {
        pushLog('网络安静，未发现新威胁。', 'success')
      }
    } catch {
      pushLog('请求异常，跳过本轮扫描。', 'warning')
    }
  }

  // ========== 开关监控 ==========
  function startMonitor() {
    if (isMonitoring.value) return
    isMonitoring.value = true
    pushLog('🟢 启动实时多源嗅探雷达...', 'success')
    pushLog('监听 IPFS Swarm P2P 流量中...', 'info')
    performScan()
    monitorInterval = setInterval(performScan, 8000)
  }

  function stopMonitor() {
    if (!isMonitoring.value) return
    isMonitoring.value = false
    if (monitorInterval) {
      clearInterval(monitorInterval)
      monitorInterval = null
    }
    pushLog('🔴 实时嗅探雷达已关闭。', 'warning')
  }

  function toggleMonitor() {
    if (isMonitoring.value) {
      stopMonitor()
    } else {
      startMonitor()
    }
  }

  return {
    isMonitoring,
    scanLogs,
    clueList,
    tableLoading,
    scanKeyword,
    pushLog,
    fetchClues,
    performScan,
    startMonitor,
    stopMonitor,
    toggleMonitor
  }
})