"""
DHT/Bitswap底层嗅探模块
位置: core/collector/dht_sniffer.py
对应设计方案 3.1.1 + IF-DSS框架 Node区域 & Peer区域

职责：
1. Node区域：检查本地IPFS节点安装信息、配置、存储（IF-DSS 4.2.2）
2. Peer区域：通过Swarm/Bitswap/DHT嗅探网络活动（IF-DSS 4.2.1）
3. 标识符发现：提取节点ID、IP地址等（IF-DSS 4.3.2）

前提：本地需运行 IPFS Desktop 或 ipfs daemon
"""

import os
import re
import json
import random
import logging
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class DHTSniffer:
    """本地IPFS节点DHT/Bitswap嗅探器"""

    IPFS_API = "http://127.0.0.1:5001/api/v0"

    # CID正则
    CID_PATTERN = re.compile(
        r'(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z0-9]{55})'
    )

    def __init__(self, api_url: str = None):
        self.api_url = api_url or self.IPFS_API
        self._available = None  # 缓存可用性

    # ==================== Node区域（IF-DSS 4.2.2） ====================

    def is_available(self) -> bool:
        """检查本地IPFS节点是否可用"""
        if self._available is not None:
            return self._available

        try:
            resp = requests.post(f"{self.api_url}/id", timeout=3)
            self._available = (resp.status_code == 200)
        except Exception:
            self._available = False

        if not self._available:
            logger.warning("本地IPFS节点不可用（请启动 IPFS Desktop）")

        return self._available

    def reset_availability_cache(self):
        """重置可用性缓存，下次调用 is_available 会重新检测"""
        self._available = None

    def get_node_info(self) -> Optional[Dict]:
        """获取本地IPFS节点基本信息"""
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
                    'public_key': data.get('PublicKey', '')[:32] + '...' if data.get('PublicKey') else '',
                }
        except Exception as e:
            logger.error(f"获取节点信息失败: {e}")
        return None

    def inspect_local_node(self) -> Dict:
        """
        检查本地IPFS节点安装信息（IF-DSS 4.2.2 Collecting local artifacts）

        采集：
        - 安装目录路径和是否存在
        - 配置文件中的关键设置（API地址、网关地址、Swarm监听）
        - 节点Peer ID
        - 数据存储目录大小
        - 私钥文件是否存在（不读取内容，仅检测）
        """
        # IPFS默认安装目录
        ipfs_path = os.environ.get(
            'IPFS_PATH',
            os.path.expanduser('~/.ipfs')
        )

        result = {
            'ipfs_path': ipfs_path,
            'exists': os.path.exists(ipfs_path),
            'config': None,
            'peer_id': None,
            'private_key_exists': False,
            'datastore_size': None,
            'datastore_size_human': '',
            'repo_version': None,
        }

        if not result['exists']:
            logger.info(f"IPFS安装目录不存在: {ipfs_path}")
            return result

        # 读取配置文件
        config_path = os.path.join(ipfs_path, 'config')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                result['peer_id'] = config.get('Identity', {}).get('PeerID')
                result['private_key_exists'] = bool(
                    config.get('Identity', {}).get('PrivKey')
                )
                result['config'] = {
                    'api_addr': config.get('Addresses', {}).get('API'),
                    'gateway_addr': config.get('Addresses', {}).get('Gateway'),
                    'swarm_addrs': config.get('Addresses', {}).get('Swarm', []),
                    'storage_max': config.get('Datastore', {}).get('StorageMax'),
                    'bootstrap_peers': len(
                        config.get('Bootstrap', [])
                    ),
                }
            except Exception as e:
                logger.warning(f"读取IPFS配置失败: {e}")

        # repo版本
        version_path = os.path.join(ipfs_path, 'version')
        if os.path.exists(version_path):
            try:
                with open(version_path, 'r') as f:
                    result['repo_version'] = f.read().strip()
            except Exception:
                pass

        # 数据目录大小
        blocks_path = os.path.join(ipfs_path, 'blocks')
        if os.path.exists(blocks_path):
            try:
                total = 0
                file_count = 0
                for dp, _, filenames in os.walk(blocks_path):
                    for fn in filenames:
                        fp = os.path.join(dp, fn)
                        total += os.path.getsize(fp)
                        file_count += 1
                result['datastore_size'] = total
                result['datastore_size_human'] = self._format_size(total)
                result['block_file_count'] = file_count
            except Exception as e:
                logger.warning(f"计算数据目录大小失败: {e}")

        logger.info(
            f"[Node区域] 本地节点检查完成: "
            f"PeerID={result['peer_id'][:16] if result['peer_id'] else 'N/A'}..."
        )
        return result

    # ==================== Peer区域（IF-DSS 4.2.1） ====================

    def get_connected_peers(self) -> List[Dict]:
        """
        获取当前连接的全球对等节点

        Returns:
            [{'Peer': 'Qm...', 'Addr': '/ip4/...', ...}, ...]
        """
        if not self.is_available():
            return []

        try:
            resp = requests.post(
                f"{self.api_url}/swarm/peers", timeout=5
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
        嗅探随机对等节点的Bitswap Wantlist（IF-DSS 4.2.1 Peer network monitoring）

        Wantlist = 节点当前正在请求的CID列表
        代表网络中正在被传输的内容

        Args:
            max_peers: 最多嗅探多少个节点

        Returns:
            [{'cid': 'Qm...', 'source': '...', 'keyword': '...'}, ...]
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
            logger.info(
                f"[Peer区域] Bitswap Wantlist嗅探发现 {len(discovered)} 个CID"
            )

        return discovered

    def find_providers(self, cid: str, num_providers: int = 10) -> List[Dict]:
        """
        查找特定CID的提供者节点（IF-DSS 4.2.1 Dedicated software）

        使用IPFS DHT findprovs命令，定位内容提供者的节点ID和IP地址

        Args:
            cid: 要查找的CID
            num_providers: 最多返回多少个提供者

        Returns:
            [{'peer_id': '...', 'addresses': [...]}]
        """
        if not self.is_available():
            return []

        providers = []

        try:
            # 第一步：findprovs 找到提供者节点ID
            resp = requests.post(
                f"{self.api_url}/dht/findprovs",
                params={'arg': cid, 'num-providers': num_providers},
                timeout=30,
                stream=True
            )

            provider_ids = []
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    responses = data.get('Responses') or []
                    for r in responses:
                        pid = r.get('ID', '')
                        if pid and pid not in provider_ids:
                            provider_ids.append(pid)
                except Exception:
                    continue

            # 第二步：findpeer 找到每个提供者的IP地址
            for pid in provider_ids[:num_providers]:
                peer_info = {'peer_id': pid, 'addresses': []}
                try:
                    resp2 = requests.post(
                        f"{self.api_url}/dht/findpeer",
                        params={'arg': pid},
                        timeout=10,
                        stream=True
                    )
                    for line2 in resp2.iter_lines():
                        if not line2:
                            continue
                        try:
                            data2 = json.loads(line2)
                            resps2 = data2.get('Responses') or []
                            for r2 in resps2:
                                addrs = r2.get('Addrs') or []
                                peer_info['addresses'].extend(addrs)
                        except Exception:
                            continue
                except Exception:
                    pass

                providers.append(peer_info)

            logger.info(
                f"CID {cid[:20]}... 找到 {len(providers)} 个提供者节点"
            )

        except Exception as e:
            logger.error(f"FindProvs失败: {e}")

        return providers

    def get_bitswap_stats(self) -> Optional[Dict]:
        """获取本地节点的Bitswap统计（传输数据量等）"""
        if not self.is_available():
            return None

        try:
            resp = requests.post(
                f"{self.api_url}/bitswap/stat", timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    'blocks_received': data.get('BlocksReceived', 0),
                    'blocks_sent': data.get('BlocksSent', 0),
                    'data_received': data.get('DataReceived', 0),
                    'data_received_human': self._format_size(
                        data.get('DataReceived', 0)
                    ),
                    'data_sent': data.get('DataSent', 0),
                    'data_sent_human': self._format_size(
                        data.get('DataSent', 0)
                    ),
                    'peers_count': len(data.get('Peers', [])),
                    'wantlist_size': len(data.get('Wantlist', [])),
                }
        except Exception:
            pass
        return None

    # ==================== 辅助方法 ====================

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(units) - 1:
            size /= 1024
            i += 1
        return f"{size:.1f} {units[i]}"