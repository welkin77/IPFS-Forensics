/* 极少量JS：只有ECharts和终端自动滚动需要 */

// 终端自动滚到底部（HTMX内容变化后触发）
document.addEventListener('htmx:afterSwap', function(event) {
    var log = document.getElementById('scan-log');
    if (log && event.target.id === 'scan-log') {
        log.scrollTop = log.scrollHeight;
    }
});

// 引擎状态的HTMX响应处理（纯文本替换为HTML）
document.addEventListener('htmx:beforeSwap', function(event) {
    if (event.target.id === 'engine-status') {
        // 将JSON转为HTML展示
        try {
            var data = JSON.parse(event.detail.xhr.responseText);
            var html = '<div class="d-flex justify-content-between"><span>累计扫描:</span><strong>' + data.scan_count + ' 次</strong></div>';
            html += '<div class="d-flex justify-content-between"><span>已知CID:</span><strong>' + data.known_cids_count + ' 个</strong></div>';
            html += '<div class="d-flex justify-content-between"><span>IPFS节点:</span><strong>';
            if (data.ipfs_node_available) {
                html += '<span class="text-success">● 在线 (' + data.connected_peers + ')</span>';
            } else {
                html += '<span class="text-danger">● 离线</span>';
            }
            html += '</strong></div>';
            if (data.last_scan_time) {
                html += '<div class="d-flex justify-content-between"><span>上次扫描:</span><span class="text-muted">' + data.last_scan_time + '</span></div>';
            }
            event.detail.serverResponse = html;
        } catch(e) {}
    }
});