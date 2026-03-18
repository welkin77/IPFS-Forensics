<template>
  <div class="report-wrapper">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <el-button type="primary" icon="Download" @click="downloadPDF">下载电子数据取证报告 (PDF)</el-button>
    </div>

    <!-- A4 纸张样式的报告容器 -->
    <div id="pdf-content" class="a4-paper">
      <h1 class="report-title">电子数据取证与分析报告</h1>
      <div class="report-subtitle">
        报告编号：{{ reportData?.case_info?.case_id || 'UNKNOWN' }} | 
        生成时间：{{ formatTime(reportData?.case_info?.generation_time) }}
      </div>

      <el-divider />

      <div class="section">
        <h3 class="section-title">一、 基本案情与取证摘要</h3>
        <table class="info-table">
          <tbody>
            <tr><th>案件编号</th><td>{{ reportData?.case_info?.case_id }}</td><th>取证人员</th><td>System_API</td></tr>
            <tr><th>目标 CID</th><td colspan="3" class="mono">{{ reportData?.evidence_summary?.cid }}</td></tr>
            <tr><th>文件大小</th><td>{{ reportData?.evidence_summary?.file_size_bytes }} Bytes</td><th>文件类型</th><td>{{ reportData?.analysis_results?.file_type }}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="section">
        <h3 class="section-title">二、 司法哈希与完整性校验</h3>
        <p>本系统采用多重哈希算法对固定后的电子数据进行完整性校验，并构建默克尔树防篡改。</p>
        <table class="info-table">
          <tbody>
            <tr><th>SHA-256</th><td class="mono">{{ reportData?.evidence_summary?.hash_values?.sha256 }}</td></tr>
            <tr><th>SHA-512</th><td class="mono">{{ reportData?.evidence_summary?.hash_values?.sha512 }}</td></tr>
            <tr><th>默克尔树根</th><td class="mono text-bold">{{ reportData?.verification_proof?.merkle_root }}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="section">
        <h3 class="section-title">三、 内容审查与违法判定</h3>
        <div class="audit-box" :class="reportData?.analysis_results?.is_illegal ? 'danger' : 'safe'">
          <strong>审查结果：</strong> 
          {{ reportData?.analysis_results?.is_illegal ? '发现违法违规内容！' : '未发现明显违规特征。' }}
          <br/><br/>
          <strong>命中特征词：</strong> 
          {{ reportData?.analysis_results?.matched_keywords?.join(', ') || '无' }}
        </div>
        <p class="text-summary"><strong>提取文本摘要：</strong><br/>{{ reportData?.analysis_results?.extracted_text || '无可用文本' }}</p>
      </div>

      <div class="section">
        <h3 class="section-title">四、 监管链 (Chain of Custody) 审计记录</h3>
        <table class="info-table">
          <tbody>
            <tr><th>时间</th><th>操作动作</th><th>操作人</th><th>防篡改审计摘要 (Hash)</th></tr>
            <tr v-for="(record, idx) in reportData?.chain_of_custody" :key="idx">
              <td>{{ formatTime(record.timestamp) }}</td>
              <td>{{ record.action }}</td>
              <td>{{ record.operator }}</td>
              <td class="mono">{{ record.record_hash.substring(0, 16) }}...</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="signature-area">
        <p><strong>技术鉴定人签字：</strong> _________________</p>
        <p><strong>日期：</strong> _________________</p>
        <div class="official-seal">司法鉴定专用章 (模拟)</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import html2pdf from 'html2pdf.js'
import { ElMessage } from 'element-plus'

const props = defineProps({
  reportData: {
    type: Object,
    required: true
  }
})

const formatTime = (isoString?: string) => {
  if (!isoString) return ''
  return new Date(isoString).toLocaleString()
}

const downloadPDF = () => {
  const element = document.getElementById('pdf-content')
  const opt = {
    margin:       10,
    filename:     `取证报告_${props.reportData.case_info.case_id}.pdf`,
    image:        { type: 'jpeg', quality: 0.98 },
    html2canvas:  { scale: 2 },
    jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
  }
  
  ElMessage.success('正在生成 PDF，请稍候...')
  html2pdf().set(opt).from(element).save()
}
</script>

<style scoped>
.report-wrapper {
  background: #f0f2f5;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.toolbar {
  margin-bottom: 20px;
  width: 210mm;
  display: flex;
  justify-content: flex-end;
}
.a4-paper {
  background: white;
  width: 210mm;
  min-height: 297mm;
  padding: 20mm;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  box-sizing: border-box;
  color: #333;
  font-family: 'SimSun', '宋体', serif;
}
.report-title {
  text-align: center;
  font-size: 28px;
  letter-spacing: 2px;
  margin-bottom: 10px;
}
.report-subtitle {
  text-align: center;
  font-size: 12px;
  color: #666;
  margin-bottom: 20px;
}
.section {
  margin-bottom: 30px;
}
.section-title {
  font-size: 18px;
  border-left: 4px solid #409EFF;
  padding-left: 10px;
  margin-bottom: 15px;
}
.info-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.info-table th, .info-table td {
  border: 1px solid #333;
  padding: 8px;
  text-align: left;
}
.info-table th {
  background-color: #f8f8f8;
  width: 15%;
}
.mono {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}
.text-bold {
  font-weight: bold;
}
.audit-box {
  padding: 15px;
  border: 2px dashed #ccc;
  font-size: 14px;
}
.audit-box.danger {
  border-color: #F56C6C;
  background-color: #fef0f0;
  color: #F56C6C;
}
.audit-box.safe {
  border-color: #67C23A;
  background-color: #f0f9eb;
}
.text-summary {
  margin-top: 15px;
  font-size: 12px;
  color: #666;
  background: #f9f9f9;
  padding: 10px;
}
.signature-area {
  margin-top: 50px;
  text-align: right;
  position: relative;
}
.official-seal {
  position: absolute;
  right: 50px;
  top: -20px;
  width: 120px;
  height: 120px;
  border: 4px solid #F56C6C;
  border-radius: 50%;
  color: #F56C6C;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 16px;
  transform: rotate(-15deg);
  opacity: 0.6;
}
</style>