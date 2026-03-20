# src/analyzer/credential_extractor.py
"""
新增模块：从IPFS安装目录提取凭证信息
IF-DSS完全没有此功能
"""

import json
import os
import shutil
from pathlib import Path


def extract_peer_id(config_path: str) -> str:
    """从IPFS config文件提取PeerID"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get("Identity", {}).get("PeerID", "")
    except Exception as e:
        print(f"[ERROR] Cannot read config: {e}")
        return ""


def extract_private_key(config_path: str) -> str:
    """从IPFS config文件提取私钥（Base64编码）"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get("Identity", {}).get("PrivKey", "")
    except Exception as e:
        print(f"[ERROR] Cannot read config: {e}")
        return ""


def extract_api_address(config_path: str) -> str:
    """提取API监听地址"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get("Addresses", {}).get("API", "")
    except Exception:
        return ""


def extract_swarm_key(repo_path: str) -> bytes:
    """提取swarm.key（私有网络密钥）"""
    key_path = os.path.join(repo_path, "swarm.key")
    if os.path.exists(key_path):
        with open(key_path, 'rb') as f:
            return f.read()
    return None


def clone_credentials(source_repo: str, target_dir: str) -> dict:
    """
    凭证克隆：将IPFS仓库的关键凭证文件复制到调查用目录

    对应IF-DSS论文中的 "Credential Cloning" 步骤
    """
    result = {"cloned_files": [], "peer_id": None}
    os.makedirs(target_dir, exist_ok=True)

    # 复制config
    config_src = os.path.join(source_repo, "config")
    if os.path.exists(config_src):
        config_dst = os.path.join(target_dir, "config")
        shutil.copy2(config_src, config_dst)
        result["cloned_files"].append("config")
        result["peer_id"] = extract_peer_id(config_src)

    # 复制keystore目录
    keystore_src = os.path.join(source_repo, "keystore")
    if os.path.exists(keystore_src):
        keystore_dst = os.path.join(target_dir, "keystore")
        shutil.copytree(keystore_src, keystore_dst, dirs_exist_ok=True)
        result["cloned_files"].append("keystore/")

    # 复制swarm.key
    swarm_src = os.path.join(source_repo, "swarm.key")
    if os.path.exists(swarm_src):
        shutil.copy2(swarm_src, os.path.join(target_dir, "swarm.key"))
        result["cloned_files"].append("swarm.key")

    # 复制datastore_spec
    ds_src = os.path.join(source_repo, "datastore_spec")
    if os.path.exists(ds_src):
        shutil.copy2(ds_src, os.path.join(target_dir, "datastore_spec"))
        result["cloned_files"].append("datastore_spec")

    print(f"[OK] Cloned {len(result['cloned_files'])} items to {target_dir}")
    return result


def summarize_credentials(repo_path: str) -> dict:
    """汇总IPFS仓库的所有凭证信息"""
    config_path = os.path.join(repo_path, "config")

    summary = {
        "repo_path": repo_path,
        "peer_id": extract_peer_id(config_path),
        "has_private_key": bool(extract_private_key(config_path)),
        "api_address": extract_api_address(config_path),
        "has_swarm_key": os.path.exists(os.path.join(repo_path, "swarm.key")),
        "has_keystore": os.path.exists(os.path.join(repo_path, "keystore")),
    }

    return summary