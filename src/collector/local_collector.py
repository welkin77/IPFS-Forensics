# src/collector/local_collector.py  
"""本地IPFS仓库采集（IF-DSS完全没有）"""
import json, shutil, os
from ..integrity.hasher import compute_hash

def collect_ipfs_repo(repo_path: str, output_dir: str) -> dict:
    """采集IPFS安装目录的关键文件"""
    evidence = {}
    manifest_path = os.path.join(output_dir, "evidence_hashes.json")
    
    # 1. 采集config（含PeerID和私钥）
    config_path = os.path.join(repo_path, "config")
    if os.path.exists(config_path):
        dst = os.path.join(output_dir, "config.json")
        shutil.copy2(config_path, dst)
        evidence["config"] = compute_hash(dst, manifest_path)
        
        # 提取PeerID
        config = json.load(open(config_path))
        evidence["peer_id"] = config.get("Identity", {}).get("PeerID")
    
    # 2. 采集blocks目录
    blocks_dir = os.path.join(repo_path, "blocks")
    if os.path.exists(blocks_dir):
        dst_blocks = os.path.join(output_dir, "blocks")
        shutil.copytree(blocks_dir, dst_blocks, dirs_exist_ok=True)
        block_count = sum(1 for _, _, files in os.walk(dst_blocks) 
                         for f in files if f.endswith('.data'))
        evidence["blocks_count"] = block_count
    
    return evidence