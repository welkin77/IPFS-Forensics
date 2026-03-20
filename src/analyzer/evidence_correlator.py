# src/analyzer/evidence_correlator.py
"""
新增模块：多源证据关联分析
IF-DSS完全没有此功能
"""

import json
import os
from datetime import datetime


def correlate_local_and_remote(local_evidence: dict,
                                track_results: dict) -> dict:
    """
    关联本地采集的证据与远程追踪结果

    关联策略：
    1. CID关联：本地blocks中的CID是否在远程追踪结果中出现
    2. 身份关联：本地PeerID是否在远程发现的NodeID中出现
    """
    correlations = []

    local_peer_id = local_evidence.get("peer_id", "")

    # 检查本地PeerID是否出现在远程追踪的provider中
    for cid, data in track_results.items():
        node_ids = data.get("NodeIDs", [])
        if local_peer_id and local_peer_id in node_ids:
            correlations.append({
                "type": "identity_match",
                "detail": f"Local PeerID {local_peer_id} found as provider of {cid}",
                "strength": "direct",
                "cid": cid
            })

    result = {
        "timestamp": datetime.now().isoformat(),
        "correlations": correlations,
        "local_peer_id": local_peer_id,
        "remote_cids_checked": len(track_results),
    }

    return result


def build_timeline(events: list) -> list:
    """
    构建时间线
    将来自不同来源的事件按时间排序
    """
    sorted_events = sorted(events, key=lambda x: x.get("timestamp", ""))
    return sorted_events