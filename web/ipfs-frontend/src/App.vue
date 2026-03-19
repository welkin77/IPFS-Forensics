<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="aside">
      <div class="logo">
        <h2>IPFS 取证系统</h2>
      </div>
      <el-menu
        default-active="/evidence"
        class="el-menu-vertical"
        background-color="#304156"
        text-color="#bfcbd9"
        active-text-color="#409EFF"
        router
      >
        <el-menu-item index="/gather">
          <el-icon><Monitor /></el-icon>
          <span>全网情报采集</span>
          <!-- ★ 改动1：侧边栏显示雷达运行状态 -->
          <span v-if="radarStore.isMonitoring" class="radar-badge">● 扫描中</span>
        </el-menu-item>
        <el-menu-item index="/evidence">
          <el-icon><Document /></el-icon>
          <span>证据固定提取</span>
        </el-menu-item>
        <el-menu-item index="/dashboard">
          <el-icon><DataBoard /></el-icon>
          <span>大盘与历史案件</span>
        </el-menu-item>
        <el-menu-item index="/analysis">
          <el-icon><Share /></el-icon>
          <span>身份画像分析 (开发中)</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-right">
          <el-icon :size="20"><Avatar /></el-icon>
          <span style="margin-left: 8px;">警员号: Police_001</span>
        </div>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<!-- ★ 改动2：加 script 导入 store -->
<script setup lang="ts">
import { useRadarStore } from './stores/radar'
const radarStore = useRadarStore()
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.aside {
  background-color: #304156;
}
.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  border-bottom: 1px solid #1f2d3d;
}
.el-menu-vertical {
  border-right: none;
}
.header {
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 20px;
}
.header-right {
  display: flex;
  align-items: center;
  color: #606266;
}
.main-content {
  background-color: #f0f2f5;
  padding: 20px;
}

/* ★ 新增：雷达状态徽标样式 */
.radar-badge {
  margin-left: 6px;
  color: #67c23a;
  font-size: 12px;
  animation: radar-blink 1.5s ease-in-out infinite;
}
@keyframes radar-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
</style>

<style>
/* 全局样式重置 */
body {
  margin: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
}
</style>