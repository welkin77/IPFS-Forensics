# setup_private_network.ps1
# 用法: powershell -ExecutionPolicy Bypass -File setup_private_network.ps1

Write-Host "========================================="
Write-Host "  IPFS 私有网络搭建脚本 (Windows)"
Write-Host "========================================="

# ---- 配置区 ----
$BASE_DIR = "$env:USERPROFILE\ipfs-forensics-testnet"
$NODE1_DIR = "$BASE_DIR\node1-suspect"
$NODE2_DIR = "$BASE_DIR\node2-investigator"
$NODE3_DIR = "$BASE_DIR\node3-observer"

# ---- 清理 ----
Write-Host "[1/7] 清理旧环境..."
Get-Process -Name "ipfs" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
if (Test-Path $BASE_DIR) { Remove-Item -Recurse -Force $BASE_DIR }
New-Item -ItemType Directory -Path $BASE_DIR | Out-Null

# ---- 生成swarm key ----
Write-Host "[2/7] 生成swarm key..."
python -c @"
import secrets
key = secrets.token_hex(32)
with open(r'$BASE_DIR\swarm.key', 'w', newline='\n') as f:
    f.write(f'/key/swarm/psk/1.0.0/\n/base16/\n{key}\n')
print('  swarm.key generated')
"@

# ---- 初始化节点 ----
Write-Host "[3/7] 初始化节点..."

# 节点1
$env:IPFS_PATH = $NODE1_DIR
ipfs init --profile=server 2>$null
Copy-Item "$BASE_DIR\swarm.key" "$NODE1_DIR\"
ipfs config Addresses.API "/ip4/127.0.0.1/tcp/5001"
ipfs config Addresses.Gateway "/ip4/127.0.0.1/tcp/8080"
ipfs config Addresses.Swarm --json '["/ip4/0.0.0.0/tcp/4001", "/ip4/0.0.0.0/udp/4001/quic-v1"]'
ipfs bootstrap rm --all 2>$null
Write-Host "  节点1(嫌疑人) OK - API:5001"

# 节点2
$env:IPFS_PATH = $NODE2_DIR
ipfs init --profile=server 2>$null
Copy-Item "$BASE_DIR\swarm.key" "$NODE2_DIR\"
ipfs config Addresses.API "/ip4/127.0.0.1/tcp/5002"
ipfs config Addresses.Gateway "/ip4/127.0.0.1/tcp/8081"
ipfs config Addresses.Swarm --json '["/ip4/0.0.0.0/tcp/4002", "/ip4/0.0.0.0/udp/4002/quic-v1"]'
ipfs bootstrap rm --all 2>$null
Write-Host "  节点2(调查员) OK - API:5002"

# 节点3
$env:IPFS_PATH = $NODE3_DIR
ipfs init --profile=server 2>$null
Copy-Item "$BASE_DIR\swarm.key" "$NODE3_DIR\"
ipfs config Addresses.API "/ip4/127.0.0.1/tcp/5003"
ipfs config Addresses.Gateway "/ip4/127.0.0.1/tcp/8082"
ipfs config Addresses.Swarm --json '["/ip4/0.0.0.0/tcp/4003", "/ip4/0.0.0.0/udp/4003/quic-v1"]'
ipfs bootstrap rm --all 2>$null
Write-Host "  节点3(旁观者) OK - API:5003"

# ---- 启动节点 ----
Write-Host "[4/7] 启动节点..."

$env:IPFS_PATH = $NODE1_DIR
Start-Process -FilePath "ipfs" -ArgumentList "daemon" -WindowStyle Hidden
Start-Sleep -Seconds 4

$env:IPFS_PATH = $NODE2_DIR
Start-Process -FilePath "ipfs" -ArgumentList "daemon" -WindowStyle Hidden
Start-Sleep -Seconds 4

$env:IPFS_PATH = $NODE3_DIR
Start-Process -FilePath "ipfs" -ArgumentList "daemon" -WindowStyle Hidden
Start-Sleep -Seconds 4

Write-Host "  所有节点已启动"

# ---- 连接节点 ----
Write-Host "[5/7] 连接节点..."

$env:IPFS_PATH = $NODE1_DIR
$NODE1_ID = (ipfs id -f='<id>').Trim()
Write-Host "  节点1 PeerID: $NODE1_ID"

$env:IPFS_PATH = $NODE2_DIR
ipfs swarm connect "/ip4/127.0.0.1/tcp/4001/p2p/$NODE1_ID"

$env:IPFS_PATH = $NODE3_DIR
ipfs swarm connect "/ip4/127.0.0.1/tcp/4001/p2p/$NODE1_ID"

Write-Host "  所有节点已互联"

# ---- 添加测试数据 ----
Write-Host "[6/7] 添加测试文件..."

$TEST_DIR = "$BASE_DIR\test_data"
New-Item -ItemType Directory -Path $TEST_DIR -Force | Out-Null
New-Item -ItemType Directory -Path "$TEST_DIR\website" -Force | Out-Null

# 钓鱼页面
@"
<!DOCTYPE html>
<html>
<head><title>Login - Secure Bank</title></head>
<body>
<h1>Fake Bank Login</h1>
<form>
  <input type="text" placeholder="Username">
  <input type="password" placeholder="Password">
  <button>Login</button>
</form>
</body>
</html>
"@ | Out-File -FilePath "$TEST_DIR\phishing.html" -Encoding utf8

# 大文件（用于多块重组测试）
python -c @"
import random, string
content = ''.join(random.choices(string.ascii_letters + string.digits, k=500000))
with open(r'$TEST_DIR\large_file.txt', 'w') as f:
    f.write(content)
"@

# 网站目录
"<html><body><h1>Test</h1></body></html>" | Out-File "$TEST_DIR\website\index.html" -Encoding utf8
"<html><body><h1>Page 2</h1></body></html>" | Out-File "$TEST_DIR\website\page2.html" -Encoding utf8

$env:IPFS_PATH = $NODE1_DIR
$CID_PHISHING = (ipfs add -q "$TEST_DIR\phishing.html").Trim()
$CID_LARGE = (ipfs add -q "$TEST_DIR\large_file.txt").Trim()
$CID_WEBSITE = (ipfs add -r -q "$TEST_DIR\website" | Select-Object -Last 1).Trim()

Write-Host "  钓鱼页面 CID: $CID_PHISHING"
Write-Host "  大文件 CID:   $CID_LARGE"
Write-Host "  网站目录 CID: $CID_WEBSITE"

# ---- 验证 ----
Write-Host "[7/7] 验证..."

$env:IPFS_PATH = $NODE2_DIR
$result = ipfs cat $CID_PHISHING 2>$null | Select-Object -First 1
if ($result -match "DOCTYPE") {
    Write-Host "  ✅ 验证成功！"
} else {
    Write-Host "  ❌ 验证失败"
}

# ---- 汇总 ----
Write-Host ""
Write-Host "========================================="
Write-Host "  私有网络搭建完成！"
Write-Host "========================================="
Write-Host ""
Write-Host "常用命令:"
Write-Host "  `$env:IPFS_PATH = '$NODE2_DIR'"
Write-Host "  ipfs dht findprovs $CID_PHISHING"
Write-Host "  ipfs dht findpeer $NODE1_ID"
Write-Host ""
Write-Host "查看blocks目录:"
Write-Host "  dir $NODE1_DIR\blocks\"
Write-Host ""
Write-Host "停止所有节点:"
Write-Host "  Get-Process ipfs | Stop-Process"

# 保存网络信息
@"
NODE1_DIR=$NODE1_DIR
NODE2_DIR=$NODE2_DIR
NODE3_DIR=$NODE3_DIR
NODE1_ID=$NODE1_ID
CID_PHISHING=$CID_PHISHING
CID_LARGE=$CID_LARGE
CID_WEBSITE=$CID_WEBSITE
"@ | Out-File "$BASE_DIR\network_info.txt"