# src/preventer/prevention_manager.py
"""
新增模块：预防措施
对应IF-DSS论文的Prevention阶段
"""

import os
import json
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def stop_ipfs_daemon() -> dict:
    """终止本地IPFS守护进程"""
    result = {"action": "stop_daemon", "timestamp": datetime.now().isoformat()}

    if not HAS_PSUTIL:
        print("[WARN] psutil not installed, trying ipfs shutdown command")
        os.system("ipfs shutdown")
        result["method"] = "ipfs_shutdown"
        result["status"] = "attempted"
        return result

    killed = []
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if proc.info['name'] and 'ipfs' in proc.info['name'].lower():
                proc.terminate()
                killed.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    result["method"] = "psutil_terminate"
    result["pids_terminated"] = killed
    result["status"] = "success" if killed else "no_process_found"
    return result


def generate_block_request_list(track_json_path: str, output_dir: str) -> dict:
    """
    生成四区域阻断请求清单
    对应IF-DSS论文的Prevention方法
    """
    requests = {
        "generated_at": datetime.now().isoformat(),
        "node_area": [],
        "peer_area": [],
        "gateway_area": [],
        "internet_area": [],
    }

    if not os.path.exists(track_json_path):
        print("[WARN] No track.json found")
        return requests

    with open(track_json_path, 'r') as f:
        track_data = json.load(f)

    all_ips = set()
    all_cids = set()

    for cid, data in track_data.items():
        all_cids.add(cid)
        for ip in data.get('IP', []):
            all_ips.add(ip)

    # 节点区域：向云服务商举报IP
    requests["node_area"] = [
        {"type": "cloud_hosting_report", "target": ip}
        for ip in all_ips
    ]

    # 对等区域：向Pinning服务举报CID
    requests["peer_area"] = [
        {"type": "pinning_service_report", "target": cid,
         "services": ["Pinata", "Web3.storage"]}
        for cid in all_cids
    ]

    # 网关区域：向官方网关发送abuse report
    requests["gateway_area"] = [
        {"type": "gateway_abuse_report", "target": cid,
         "gateway": "https://ipfs.io"}
        for cid in all_cids
    ]

    # 互联网区域：向ISP举报URL
    requests["internet_area"] = [
        {"type": "isp_url_block", "target_ip": ip}
        for ip in all_ips
    ]

    output_file = os.path.join(output_dir, "block_requests.json")
    json.dump(requests, open(output_file, 'w'), indent=2)
    print(f"[OK] Block requests saved to {output_file}")
    print(f"     Node area: {len(requests['node_area'])} requests")
    print(f"     Peer area: {len(requests['peer_area'])} requests")
    print(f"     Gateway area: {len(requests['gateway_area'])} requests")
    print(f"     Internet area: {len(requests['internet_area'])} requests")

    return requests