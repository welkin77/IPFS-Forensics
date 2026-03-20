# src/collector/node_tracker.py

import subprocess
import json
import os
from typing import List, Dict
from ..utils.ipfs_command import run_ipfs_command
from ..integrity.hasher import compute_hash

# IF-DSS原始的网关节点黑名单（直接保留）
GATEWAY_NODE_IDS = [
    "QmQzqxhK82kAmKvARFZSkUVS6fo9sySaiogAnx5EnZ6ZmC",
    "Qma8ddFEQWEU8ijWvdxXm3nxU7oHsRtCykAaVz8WUYhiKn",
    "12D3KooWL4oguAYeRKYL6xv8S5wMwKjLgP78FoNDMECuHY6vAkYH",
    # ... 与IF-DSS完全一致
]

def find_providers(cid: str, ipfs_path: str = "ipfs") -> List[str]:
    """
    重构IF-DSS findprovs()
    
    IF-DSS原始：subprocess.check_output，无异常处理
    v3改进：统一命令封装，异常处理，返回结构化结果
    """
    try:
        output = run_ipfs_command(["routing", "findprovs", cid], ipfs_path)
        node_ids = list(dict.fromkeys(output.strip().split("\n")))
        return [nid for nid in node_ids if nid]  # 去空
    except Exception as e:
        print(f"[WARN] findprovs failed for {cid}: {e}")
        return []

def find_peer_ips(node_ids: List[str], ipfs_path: str = "ipfs") -> List[str]:
    """
    重构IF-DSS findpeer()
    
    IF-DSS原始：无异常处理，遇到离线节点直接崩溃
    你的修复：加了try/except（已验证有效）
    v3：保留你的修复，增加结构化输出
    """
    ip_list = []
    for node_id in node_ids:
        if node_id in GATEWAY_NODE_IDS:
            continue
        try:
            output = run_ipfs_command(
                ["routing", "findpeer", node_id], ipfs_path
            )
            for line in output.split('\n'):
                if "ip4" in line:
                    ip = line.split('/')[2]
                    prefix = ip.split('.')[0]
                    if prefix not in ['10', '127', '172', '192']:
                        ip_list.append(ip)
        except subprocess.CalledProcessError:
            print(f"[WARN] Node {node_id} not found (Routing Not Found)")
            continue
        except Exception as e:
            print(f"[ERROR] Error querying {node_id}: {e}")
            continue
    
    return list(dict.fromkeys(ip_list))  # 去重（与IF-DSS一致）

def track_cids(cid_file: str, ipfs_path: str = "ipfs", 
               output_dir: str = "output") -> Dict:
    """
    重构IF-DSS node_track()
    
    IF-DSS原始：读文件→提取CID→findprovs→findpeer→保存JSON
    v3改进：返回结构化结果，增加统计信息，自动保存中间结果
    """
    # URL_to_CID逻辑直接复用IF-DSS
    cid_list = _extract_cids_from_file(cid_file)
    cid_list = list(set(cid_list))
    
    result = {}
    stats = {"total": len(cid_list), "found": 0, "not_found": 0}
    
    for cid in cid_list:
        node_ids = find_providers(cid, ipfs_path)
        if node_ids:
            ips = find_peer_ips(node_ids, ipfs_path)
            result[cid] = {"IP": ips, "NodeIDs": node_ids}
            stats["found"] += 1
            print(f"{cid} → {len(ips)} IPs found")
        else:
            stats["not_found"] += 1
            print(f"{cid} → provider not found")
        
        # 保存中间结果（与IF-DSS一致，防止daemon中断丢失数据）
        json.dump(result, open(os.path.join(output_dir, "track.json"), "w"))
    
    # v3新增：对结果文件计算哈希
    result_path = os.path.join(output_dir, "track.json")
    compute_hash(result_path, os.path.join(output_dir, "evidence_hashes.json"))
    
    return {"results": result, "stats": stats}

def _extract_cids_from_file(file_path: str) -> List[str]:
    """直接复用IF-DSS URL_to_CID()逻辑"""
    cid_list = []
    with open(file_path, "r") as fd:
        for line in fd:
            line = line.strip()
            if "Qm" in line:
                idx = line.find("Qm")
                if len(line[idx:idx+46]) == 46:
                    cid_list.append(line[idx:idx+46])
            elif "baf" in line:
                idx = line.find("baf")
                if len(line[idx:idx+59]) == 59:
                    cid_list.append(line[idx:idx+59])
    return cid_list