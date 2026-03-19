"""
DHT/Bitswap底层嗅探模块
位置: core/collector/dht_sniffer.py
对应设计方案 3.1.1

职责：通过本地IPFS节点API嗅探DHT网络中的活动
前提：本地需运行 IPFS Desktop 或 ipfs daemon

嗅探方式：
1. Swarm Peers: 获取当前连接的全球对等节点
2. Bitswap Wantlist: 查询节点正在请求的CID（Wantlist）
3. DHT FindProvs: 查找特定CID的提供者节点
"""

import re
import random
import logging
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class DHTSniffer:
    """本地IPFS节点DHT/Bitswap嗅探器"""

    IPFS_API = "http://127.0.0.1:5001/api/v0"

    # CID正则
    CID_PATTERN = re.compile(r'(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z0-9]{55})')

    def __init__(self, api_url: str = None):
        self.api_url = api_url or self.IPFS_API
        self._available = None  # 缓存可用性检测结果

    def is_available(self) -> bool:
        """检查本地IPFS节点是否可用"""
        if self._available is not None:
            return self._available

        try:
            resp = requests.post(
                f"{self.api_url}/id",
                timeout=3
            )
            self._available = (resp.status_code == 200)
        except Exception:
            self._available = False

        if not self._available:
            logger.warning("本地IPFS节点不可用（请启动 IPFS Desktop）")

        return self._available

    def get_connected_peers(self) -> List[Dict]:
        """
        获取当前连接的全球对等节点

        Returns:
            [{'peer_id': 'Qm...', 'addr': '/ip4/...'}, ...]
        """
        if not self.is_available():
            return []

        try:
            resp = requests.post(
                f"{self.api_url}/swarm/peers",
                timeout=5
            )
            if resp.status_code == 200:
                peers = resp.json().get('Peers') or []
                logger.info(f"本地IPFS节点已连接 {len(peers)} 个对等节点")
                return peers
        except Exception as e:
            logger.error(f"获取Swarm Peers失败: {e}")

        return []

    def sniff_wantlists(self, max_peers: int = 15) -> List[Dict]:
        """
        嗅探随机对等节点的Bitswap Wantlist

        Wantlist是节点当前正在请求的CID列表，
        代表网络中正在被传输的内容。

        Args:
            max_peers: 最多嗅探多少个节点

        Returns:
            [{'cid': 'Qm...', 'source': 'IPFS_Bitswap_Peer (Qm12...)', 'keyword': 'P2P底层数据流'}, ...]
        """
        peers = self.get_connected_peers()
        if not peers:
            return []

        # 随机抽样
        sample = random.sample(peers, min(max_peers, len(peers)))
        discovered = []

        for peer in sample:
            peer_id = peer.get('Peer', '')
            if not peer_id:
                continue

            try:
                resp = requests.post(
                    f"{self.api_url}/bitswap/wantlist",
                    params={'peer': peer_id},
                    timeout=3
                )

                if resp.status_code != 200:
                    continue

                keys = resp.json().get('Keys') or []

                for key_obj in keys:
                    if not isinstance(key_obj, dict):
                        continue
                    raw_cid = key_obj.get('/', '')
                    if raw_cid and self.CID_PATTERN.match(raw_cid):
                        discovered.append({
                            'cid': raw_cid,
                            'source': f"IPFS_Bitswap_Peer ({peer_id[:12]}...)",
                            'keyword': 'P2P底层数据流'
                        })

            except requests.exceptions.Timeout:
                continue
            except Exception:
                continue

        if discovered:
            logger.info(f"[DHT嗅探] 从Wantlist中发现 {len(discovered)} 个CID")

        return discovered

    def find_providers(self, cid: str, num_providers: int = 10) -> List[str]:
        """
        查找特定CID的提供者节点

        Args:
            cid: 要查找的CID
            num_providers: 最多返回多少个提供者

        Returns:
            提供者Peer ID列表
        """
        if not self.is_available():
            return []

        try:
            resp = requests.post(
                f"{self.api_url}/dht/findprovs",
                params={'arg': cid, 'num-providers': num_providers},
                timeout=30,
                stream=True  # findprovs是流式返回
            )

            providers = []
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    import json
                    data = json.loads(line)
                    responses = data.get('Responses') or []
                    for r in responses:
                        pid = r.get('ID', '')
                        if pid and pid not in providers:
                            providers.append(pid)
                except Exception:
                    continue

            logger.info(f"CID {cid[:20]}... 找到 {len(providers)} 个提供者")
            return providers

        except Exception as e:
            logger.error(f"FindProvs失败: {e}")
            return []

    def get_node_info(self) -> Optional[Dict]:
        """获取本地IPFS节点信息"""
        if not self.is_available():
            return None

        try:
            resp = requests.post(f"{self.api_url}/id", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'peer_id': data.get('ID', ''),
                    'agent_version': data.get('AgentVersion', ''),
                    'protocol_version': data.get('ProtocolVersion', ''),
                    'addresses': data.get('Addresses', []),
                }
        except Exception:
            pass
        return None