<template>
  <div class="dashboard-container">
    <!-- 顶部统计卡片 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">总取证数量</div>
          <div class="stat-value text-primary">{{ tableData.length }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">发现非法文件</div>
          <div class="stat-value text-danger">{{ illegalCount }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-title">最新监控节点</div>
          <div class="stat-value text-success">正常运行中</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 历史数据表格 -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <span>历史案件证据固化库</span>
          <el-button type="primary" size="small" @click="fetchData" icon="Refresh">刷新数据</el-button>
        </div>
      </template>

      <el-table :data="tableData" style="width: 100%" border stripe height="calc(100vh - 300px)">
        <el-table-column prop="id" label="ID" width="60" align="center" />
        
        <el-table-column prop="case_id" label="案件编号" width="160">
          <template #default="scope">
            <strong>{{ scope.row.case_id }}</strong>
          </template>
        </el-table-column>
        
        <el-table-column prop="cid" label="IPFS CID" show-overflow-tooltip>
          <template #default="scope">
            <span class="cid-text">{{ scope.row.cid }}</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="file_type" label="文件类型" width="120">
          <template #default="scope">
            <el-tag size="small" type="info">{{ scope.row.file_type }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="内容审查结果" width="180" align="center">
          <template #default="scope">
            <el-tag v-if="!scope.row.is_illegal" type="success" effect="dark">安全合规</el-tag>
            <el-tag v-else type="danger" effect="dark">⚠️ 发现违规</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="命中敏感词" width="180">
          <template #default="scope">
            <span v-if="!scope.row.matched_keywords">-</span>
            <div v-else class="keyword-tags">
              <el-tag 
                v-for="kw in scope.row.matched_keywords.split(',')" 
                :key="kw" 
                size="small" 
                type="warning"
              >
                {{ kw }}
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="取证时间" width="180">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>

        <!-- 查看详情操作列 -->
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="scope">
            <el-button type="primary" size="small" plain @click="viewDetail(scope.row)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ================= 豪华详情弹窗 ================= -->
    <el-dialog v-model="dialogVisible" title="历史案件取证详情溯源" width="1100px" top="5vh" destroy-on-close>
      <div v-if="currentReportData" class="detail-container">
        
        <!-- 中部左右分栏：技术概览与时间线 -->
        <el-row :gutter="20">
          <!-- 左侧：司法哈希与默克尔树证据 -->
          <el-col :span="13">
            <el-card shadow="never" class="result-card">
              <template #header><div class="card-header"><span>司法证据哈希值 (三重校验)</span></div></template>
              
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="目标 CID">
                  <span class="cid-text">{{ currentReportData.evidence_summary.cid }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="文件大小">
                  <el-tag type="info">{{ currentReportData.evidence_summary.file_size_bytes }} Bytes</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="文件审查">
                  <el-tag :type="currentReportData.analysis_results.is_illegal ? 'danger' : 'success'">
                    {{ currentReportData.analysis_results.file_type }}
                  </el-tag>
                  <el-tag v-if="currentReportData.analysis_results.is_illegal" type="danger" effect="dark" style="margin-left: 10px;">
                    ⚠️ {{ currentReportData.analysis_results.matched_keywords.join(', ') }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="提取文本">
                  <div class="text-summary-box">
                    {{ currentReportData.analysis_results.extracted_text || '无可用文本' }}
                  </div>
                </el-descriptions-item>
                <el-descriptions-item label="SHA-256">
                  <span class="hash-text">{{ currentReportData.evidence_summary.hash_values.sha256 }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="SHA-512">
                  <span class="hash-text">{{ currentReportData.evidence_summary.hash_values.sha512 }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="Keccak-256">
                  <span class="hash-text chain-hash">{{ currentReportData.evidence_summary.hash_values.keccak256 }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="Merkle Root">
                  <el-tag type="success" size="small" class="merkle-tag">
                    {{ currentReportData.verification_proof.merkle_root }}
                  </el-tag>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-col>

          <!-- 右侧：监管链时间线 -->
          <el-col :span="11">
            <el-card shadow="never" class="result-card">
              <template #header><div class="card-header"><span>监管链 (Chain of Custody)</span></div></template>
              
              <el-timeline>
                <el-timeline-item
                  v-for="(record, index) in currentReportData.chain_of_custody"
                  :key="index"
                  :timestamp="formatTime(record.timestamp)"
                  :type="index === currentReportData.chain_of_custody.length - 1 ? 'success' : 'primary'"
                  placement="top"
                >
                  <el-card shadow="hover" class="timeline-card">
                    <h4 style="margin: 0 0 8px 0; color: #303133;">{{ record.action }}</h4>
                    <p class="timeline-p"><strong>操作人:</strong> {{ record.operator }}</p>
                    <p class="timeline-p details-text"><strong>Hash:</strong> {{ record.record_hash.substring(0, 16) }}...</p>
                  </el-card>
                </el-timeline-item>
              </el-timeline>
            </el-card>
          </el-col>
        </el-row>

        <!-- 优雅的过渡分割线 -->
        <el-divider content-position="center" style="margin: 30px 0;">
          <el-icon size="18" style="vertical-align: middle; margin-right: 5px;"><DocumentChecked /></el-icon>
          <span style="font-size: 16px; font-weight: bold; color: #606266;">法定电子数据取证报告</span>
        </el-divider>

        <!-- 底部 A4 报告展示区 -->
        <div class="report-display-area">
          <ForensicReport :reportData="currentReportData" />
        </div>
        
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { evidenceApi } from '../api/index'
import { ElMessage } from 'element-plus'
import { DocumentChecked } from '@element-plus/icons-vue' 
import ForensicReport from '../components/ForensicReport.vue'

const loading = ref(false)
const tableData = ref<any[]>([])
const dialogVisible = ref(false)
const currentReportData = ref<any>(null)

const illegalCount = computed(() => {
  return tableData.value.filter(item => item.is_illegal).length
})

const fetchData = async () => {
  loading.value = true
  try {
    const res = await evidenceApi.getHistory()
    tableData.value = res
  } catch (error) {
    ElMessage.error('获取历史记录失败')
  } finally {
    loading.value = false
  }
}

const formatTime = (isoString: string) => {
  const date = new Date(isoString)
  return date.toLocaleString()
}

const viewDetail = (row: any) => {
  if (!row.report_data) {
    ElMessage.warning('该记录没有包含完整的报告数据')
    return
  }
  
  try {
    currentReportData.value = typeof row.report_data === 'string' 
      ? JSON.parse(row.report_data) 
      : row.report_data;
      
    dialogVisible.value = true
  } catch (e) {
    console.error("报告解析失败:", e)
    ElMessage.error('报告数据格式异常，无法渲染')
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.dashboard-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.stat-cards { margin-bottom: 5px; }
.stat-card { text-align: center; }
.stat-title { font-size: 14px; color: #909399; margin-bottom: 10px; }
.stat-value { font-size: 28px; font-weight: bold; }
.text-primary { color: #409EFF; }
.text-danger { color: #F56C6C; }
.text-success { color: #67C23A; }
.card-header { display: flex; justify-content: space-between; align-items: center; font-weight: bold; }
.cid-text { font-family: monospace; color: #606266; font-size: 12px; }
.keyword-tags { display: flex; flex-wrap: wrap; gap: 5px; }

/* 弹窗内的样式 */
.detail-container {
  padding: 10px;
}
.result-card {
  height: 100%;
}
.text-summary-box {
  max-height: 60px; 
  overflow-y: auto; 
  color: #606266; 
  font-size: 12px; 
  line-height: 1.4;
  background-color: #f5f7fa;
  padding: 6px;
  border-radius: 4px;
}
.hash-text {
  font-family: 'Courier New', Courier, monospace;
  word-break: break-all;
  font-size: 12px;
  color: #606266;
}
.chain-hash {
  color: #E6A23C; 
}
.merkle-tag {
  font-family: 'Courier New', Courier, monospace;
  font-weight: bold;
}
.timeline-card {
  padding: 5px;
}
.timeline-p {
  margin: 4px 0;
  font-size: 12px;
  color: #606266;
}
.details-text {
  color: #909399;
  font-family: monospace;
}
.report-display-area {
  background-color: #dcdfe6;
  padding: 20px;
  border-radius: 8px;
  box-shadow: inset 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: center;
}
</style>