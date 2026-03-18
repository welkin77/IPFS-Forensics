import axios from 'axios'

// 创建 axios 实例，指向 FastAPI 后端
const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/v1', // FastAPI 的默认地址
  timeout: 30000, // 取证下载可能较慢，设置 30 秒超时
})

// 请求拦截器（可在此处添加 Token 等）
apiClient.interceptors.request.use(config => {
  return config
}, error => {
  return Promise.reject(error)
})

// 响应拦截器
apiClient.interceptors.response.use(response => {
  return response.data
}, error => {
  console.error("API Error:", error.response?.data || error.message)
  return Promise.reject(error)
})

// === 接口定义 ===

export interface CollectParams {
  cid: string;
  investigator_id: string;
  case_id: string;
}

export const evidenceApi = {
  /**
   * 提交 CID 进行证据采集与固定
   */
  collect(data: CollectParams) {
    return apiClient.post('/evidence/collect', data)
  },
  getHistory() {
    return apiClient.get('/evidence/history')
  }
}

export interface ProfileParams {
  platform: string;
  user_id: string;
}

export const analysisApi = {
  /**
   * 提交平台和账号ID，获取跨平台关联画像
   */
  profile(data: ProfileParams) {
    return apiClient.post('/analysis/profile', data)
  }
}

export const clueApi = {
  getClues() {
    return apiClient.get('/clues/list')
  },
  triggerScan(keywords: string[]) {
    return apiClient.post('/clues/scan', { keywords })
  }
}