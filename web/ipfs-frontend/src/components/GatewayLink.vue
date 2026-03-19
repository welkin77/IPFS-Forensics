<template>
  <el-dropdown trigger="click" @command="handleCommand" class="gateway-dropdown">
    <el-button type="success" size="small" plain>
      🌐 网关直达 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          v-for="gw in gateways"
          :key="gw.name"
          :command="{ action: 'open', gw }"
        >
          <span class="gw-item">
            <span>{{ gw.label }}</span>
            <el-tag v-if="!gw.needsProxy" type="success" size="small">本地</el-tag>
            <el-tag v-else type="info" size="small">公网</el-tag>
          </span>
        </el-dropdown-item>
        <el-dropdown-item divided :command="{ action: 'copy' }">
          📋 复制本地网关链接
        </el-dropdown-item>
        <el-dropdown-item :command="{ action: 'copyAll' }">
          📋 复制所有网关链接
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  cid: string
}>()

interface GatewayInfo {
  name: string
  label: string
  url: string
  needsProxy: boolean
}

const gateways: GatewayInfo[] = [
  { name: 'local',      label: '本地节点 (127.0.0.1)',  url: 'http://127.0.0.1:8080/ipfs/', needsProxy: false },
  { name: 'ipfs.io',    label: 'ipfs.io (官方)',        url: 'https://ipfs.io/ipfs/',        needsProxy: true },
  { name: 'cloudflare', label: 'Cloudflare',            url: 'https://cloudflare-ipfs.com/ipfs/', needsProxy: true },
  { name: 'dweb',       label: 'dweb.link',             url: 'https://dweb.link/ipfs/',      needsProxy: true },
  { name: 'pinata',     label: 'Pinata Gateway',        url: 'https://gateway.pinata.cloud/ipfs/', needsProxy: true },
  { name: 'w3s',        label: 'W3s.link',              url: 'https://w3s.link/ipfs/',       needsProxy: true },
]

function handleCommand(cmd: { action: string; gw?: GatewayInfo }) {
  if (!props.cid) {
    ElMessage.warning('CID 为空')
    return
  }

  switch (cmd.action) {
    case 'open':
      if (cmd.gw) {
        const fullUrl = `${cmd.gw.url}${props.cid}`
        window.open(fullUrl, '_blank')
        ElMessage.success(`正在通过 ${cmd.gw.label} 访问...`)
      }
      break

    case 'copy':
      copyToClipboard(`http://127.0.0.1:8080/ipfs/${props.cid}`)
      break

    case 'copyAll': {
      const links = gateways.map(gw => `${gw.label}: ${gw.url}${props.cid}`).join('\n')
      copyToClipboard(links)
      break
    }
  }
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    // fallback
    const input = document.createElement('textarea')
    input.value = text
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    ElMessage.success('已复制到剪贴板')
  })
}
</script>

<style scoped>
.gateway-dropdown {
  margin-left: 6px;
}
.gw-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 200px;
  gap: 8px;
}
</style>