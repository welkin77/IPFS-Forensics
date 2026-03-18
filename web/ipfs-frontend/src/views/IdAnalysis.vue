<template>
  <div class="analysis-container">
    <!-- 顶部的搜索表单 -->
    <el-card shadow="hover" class="search-card">
      <template #header>
        <div class="card-header"><span>嫌疑人跨平台关联追踪 (ID Profiler)</span></div>
      </template>
      <el-form :inline="true" :model="form" class="search-form">
        <el-form-item label="已知平台">
          <el-select v-model="form.platform" placeholder="选择平台" style="width: 150px">
            <el-option label="Telegram" value="Telegram" />
            <el-option label="Twitter" value="Twitter" />
            <el-option label="暗网论坛" value="DarkWebForum" />
          </el-select>
        </el-form-item>
        <el-form-item label="嫌疑人账号/ID">
          <el-input v-model="form.user_id" placeholder="例如: dark_user99" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchGraphData" :loading="loading">
            开始溯源分析
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 下方的 ECharts 画布区域 -->
    <el-card shadow="never" class="graph-card" v-loading="loading">
      <!-- 结果统计 -->
      <div v-if="hasData" class="stats-bar">
        <el-tag type="danger" effect="dark">种子节点: {{ resultData.seed_node }}</el-tag>
        <el-tag type="warning" style="margin-left: 10px;">发现关联账号: {{ resultData.node_count - 1 }} 个</el-tag>
        <el-tag type="info" style="margin-left: 10px;">关联路径: {{ resultData.edge_count }} 条</el-tag>
      </div>
      
      <!-- ECharts 容器 -->
      <div ref="chartRef" class="chart-container"></div>
      
      <!-- 空状态 -->
      <el-empty v-if="!hasData && !loading" description="请输入嫌疑人信息进行全网图谱关联分析" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { analysisApi, type ProfileParams } from '../api/index'

const form = reactive<ProfileParams>({
  platform: 'Telegram',
  user_id: 'dark_user99' // 默认测试数据，与后端模拟数据对应
})

const loading = ref(false)
const hasData = ref(false)
const resultData = ref<any>(null)

// ECharts 相关的引用
const chartRef = ref<HTMLElement | null>(null)
let myChart: echarts.ECharts | null = null

// 初始化 ECharts 实例
onMounted(() => {
  if (chartRef.value) {
    myChart = echarts.init(chartRef.value)
    // 监听窗口缩放，自适应图表
    window.addEventListener('resize', () => myChart?.resize())
  }
})

// 组件销毁前清理
onBeforeUnmount(() => {
  window.removeEventListener('resize', () => myChart?.resize())
  myChart?.dispose()
})

// 核心逻辑：获取数据并渲染图表
const fetchGraphData = async () => {
  if (!form.user_id) {
    ElMessage.warning('请输入嫌疑人账号')
    return
  }

  loading.value = true
  hasData.value = false

  try {
    const res = await analysisApi.profile(form)
    resultData.value = res
    hasData.value = true
    
    // 延迟一帧，等待 DOM 渲染 v-if 后再画图
    setTimeout(() => {
      renderChart(res)
    }, 100)
    
    ElMessage.success('图谱分析完成！')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '未找到该账号的关联数据')
  } finally {
    loading.value = false
  }
}

// 使用 ECharts 渲染关系图 (Force Layout)
const renderChart = (data: any) => {
  if (!myChart) {
    myChart = echarts.init(chartRef.value!)
  }

  const seedNode = data.seed_node
  const relatedNodes = data.related_nodes

  // 1. 构建 ECharts 需要的节点 (Nodes)
  const echartsNodes = relatedNodes.map((nodeName: string) => {
    const isSeed = nodeName === seedNode
    // 简单的平台识别用于分配颜色
    let category = 0;
    if (nodeName.includes('Telegram')) category = 0;
    else if (nodeName.includes('IPFS')) category = 1;
    else category = 2;

    return {
      name: nodeName,
      symbolSize: isSeed ? 60 : 45, // 种子节点放大
      category: category,
      itemStyle: isSeed ? { borderColor: '#F56C6C', borderWidth: 3, shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.3)' } : undefined
    }
  })

  // 2. 构建 ECharts 需要的连线 (Links)
  // 因为后端目前只返回了节点列表，前端为演示效果，构建以种子节点为中心的星型拓扑连线
  const echartsLinks = relatedNodes
    .filter((nodeName: string) => nodeName !== seedNode)
    .map((nodeName: string) => ({
      source: seedNode,
      target: nodeName,
      lineStyle: { width: 2, curveness: 0.1 }
    }))

  // 3. ECharts 配置项
  const option = {
    tooltip: { formatter: '{b}' },
    legend: {
      data: ['社交媒体 (Telegram/Twitter)', '去中心化网络 (IPFS Node)', '暗网论坛'],
      textStyle: { color: '#666' }
    },
    animationDurationUpdate: 1500,
    animationEasingUpdate: 'quinticInOut',
    color: ['#409EFF', '#67C23A', '#909399'], // 节点颜色主题
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: echartsNodes,
        links: echartsLinks,
        categories: [
          { name: '社交媒体 (Telegram/Twitter)' },
          { name: '去中心化网络 (IPFS Node)' },
          { name: '暗网论坛' }
        ],
        roam: true, // 允许鼠标缩放和平移
        label: {
          show: true,
          position: 'right',
          formatter: '{b}'
        },
        force: {
          repulsion: 800,  // 节点之间的排斥力
          edgeLength: 150  // 连线的长度
        }
      }
    ]
  }

  myChart.setOption(option)
}
</script>

<style scoped>
.analysis-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: calc(100vh - 100px);
}
.card-header {
  font-weight: bold;
}
.graph-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.stats-bar {
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px dashed #ebeef5;
}
.chart-container {
  width: 100%;
  height: 500px; /* 图表高度 */
  flex: 1;
}
</style>