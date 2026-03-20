# src/collector/api_collector.py
"""
新增模块：Web3.storage和Filecoin API收集
替代IF-DSS中的JavaScript脚本（fleek.js, web3storage.js）
"""

import json
import os
from datetime import datetime

try:
    import requests as http_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def query_web3storage_status(cid: str) -> dict:
    """
    查询Web3.storage CID状态（无需认证）
    替代IF-DSS的web3storage.js

    注意：Web3.storage API可能已变更，需要测试
    """
    if not HAS_REQUESTS:
        print("[WARN] requests library not installed")
        return {}

    url = f"https://api.web3.storage/status/{cid}"
    try:
        resp = http_requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"[WARN] Web3.storage returned {resp.status_code} for {cid}")
            return {"error": resp.status_code}
    except Exception as e:
        print(f"[WARN] Web3.storage query failed: {e}")
        return {"error": str(e)}


def query_filecoin_cid_checker(cid: str) -> dict:
    """查询Filecoin CID Checker"""
    if not HAS_REQUESTS:
        return {}

    url = f"https://filecoin.tools/api/v0/cid/{cid}"
    try:
        resp = http_requests.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def collect_api_evidence(cids: list, output_dir: str) -> dict:
    """批量收集API证据"""
    results = {}

    for cid in cids:
        entry = {"cid": cid, "timestamp": datetime.now().isoformat()}

        # Web3.storage
        w3_result = query_web3storage_status(cid)
        if w3_result and "error" not in w3_result:
            entry["web3storage"] = w3_result

        # Filecoin
        fc_result = query_filecoin_cid_checker(cid)
        if fc_result and "error" not in fc_result:
            entry["filecoin"] = fc_result

        if len(entry) > 2:  # 有实际数据
            results[cid] = entry

    output_file = os.path.join(output_dir, "api_evidence.json")
    json.dump(results, open(output_file, 'w'), indent=2)
    print(f"[OK] API evidence for {len(results)}/{len(cids)} CIDs saved")

    return results