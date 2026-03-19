"""
DHT网络深度嗅探模块
位置: core/collector/dht_probe.py

功能：主动爬行IPFS DHT网络，发现节点和内容提供者
与现有 core/collector/ 下的网关监控模块并列
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

class PeerStatus(Enum):
    """节点状态"""
    DISCOVERED = "discovered"
    CONNECTED = "connected"
    PROVIDING = "providing"
    UNREACHABLE = "unreachable"


@dataclass
class PeerInfo:
    """节点信息"""
    peer_id: str
    addresses: List[str] = field(default_factory=list)
    status: PeerStatus = PeerStatus.DISCOVERED
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    provided_cids: Set[str] = field(default_factory=set)
    connection_failures: int = 0
    latency_ms: Optional[float] = None
    agent_version: Optional[str] = None
    protocols: List[str] = field(default_factory=list)

    def update_last_seen(self):
        self.last_seen = datetime.utcnow()

    def is_stale(self, max_age_hours: int = 24) -> bool:
        return (datetime.utcnow() - self.last_seen) > timedelta(hours=max_age_hours)

    def to_dict(self) -> dict:
        return {
            'peer_id': self.peer_id,
            'addresses': self.addresses,
            'status': self.status.value,
            'first_seen': self.first_seen.isoformat(),
            'last_seen': self.last_seen.isoformat(),
            'provided_cids': list(self.provided_cids),
            'connection_failures': self.connection_failures,
            'latency_ms': self.latency_ms,
            'agent_version': self.agent_version,
            'protocols': self.protocols
        }


@dataclass
class CIDRecord:
    """CID发现记录"""
    cid: str
    providers: Set[str] = field(default_factory=set)
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    provider_count_history: List[Tuple[datetime, int]] = field(default_factory=list)
    source: str = "dht"

    def add_provider(self, peer_id: str):
        self.providers.add(peer_id)
        self.last_seen = datetime.utcnow()
        self.provider_count_history.append(
            (datetime.utcnow(), len(self.providers))
        )

    def to_dict(self) -> dict:
        return {
            'cid': self.cid,
            'providers': list(self.providers),
            'provider_count': len(self.providers),
            'first_seen': self.first_seen.isoformat(),
            'last_seen': self.last_seen.isoformat(),
            'source': self.source
        }


# ==================== DHT探测器 ====================

class DHTProbe:
    """
    IPFS DHT网络深度嗅探器

    功能：
    1. 广度优先爬行DHT路由表，发现活跃节点
    2. 监控特定CID的提供者变化
    3. 发现新节点和它们提供的内容
    4. 持续监控节点活动
    """

    # IPFS官方引导节点
    BOOTSTRAP_PEERS = [
        '/dnsaddr/bootstrap.libp2p.io/p2p/QmNnooDu7bfjPFoTZYxMNLWUQJyrVwtbZg5gBMjTezGAJN',
        '/dnsaddr/bootstrap.libp2p.io/p2p/QmQCU2EcMqAqQPR2i9bChDtGNJchTbq5TbXJJ16u19uLTa',
        '/dnsaddr/bootstrap.libp2p.io/p2p/QmbLHAnMoJPWSCR5Zhtx6BHJX9KiKNN6tpvbUcqanj75Nb',
        '/dnsaddr/bootstrap.libp2p.io/p2p/QmcZf59bWwK5XFi76CZX8cbJ4BhTzzA3gU1ZjYZcYW3dwt',
        '/ip4/104.131.131.82/tcp/4001/p2p/QmaCpDMGvV2BGHeYERUEnRQAwe3N8SzbUtfsmvsqQLuvuJ',
    ]

    def __init__(
        self,
        ipfs_api_addr: str = '/ip4/127.0.0.1/tcp/5001',
        max_peers: int = 10000,
        crawl_depth: int = 3,
        crawl_concurrency: int = 10,
        provider_query_timeout: int = 30,
        peer_connect_timeout: int = 15
    ):
        self.ipfs_api_addr = ipfs_api_addr
        self.max_peers = max_peers
        self.crawl_depth = crawl_depth
        self.crawl_concurrency = crawl_concurrency
        self.provider_query_timeout = provider_query_timeout
        self.peer_connect_timeout = peer_connect_timeout

        # 数据存储
        self.peers: Dict[str, PeerInfo] = {}
        self.cid_records: Dict[str, CIDRecord] = {}
        self.watched_cids: Set[str] = set()

        # 爬行状态
        self._crawl_queue: Optional[asyncio.Queue] = None
        self._visited_peers: Set[str] = set()
        self._is_crawling: bool = False
        self._crawl_stats = {
            'total_discovered': 0,
            'total_connected': 0,
            'total_failed': 0,
            'crawl_rounds': 0,
            'last_crawl_time': None
        }

        # 回调
        self._on_new_peer_callbacks = []
        self._on_new_cid_callbacks = []
        self._on_provider_change_callbacks = []

        # IPFS客户端（延迟初始化）
        self._client = None

    # ==================== 连接管理 ====================

    def _get_client(self):
        """获取IPFS客户端，带重连"""
        if self._client is None:
            try:
                import ipfshttpclient
                self._client = ipfshttpclient.connect(
                    self.ipfs_api_addr,
                    timeout=self.peer_connect_timeout
                )
                logger.info(f"已连接IPFS节点: {self.ipfs_api_addr}")
            except Exception as e:
                logger.error(f"无法连接IPFS节点 {self.ipfs_api_addr}: {e}")
                raise
        return self._client

    def _reconnect(self):
        """重连"""
        logger.warning("尝试重连IPFS节点...")
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        return self._get_client()

    def _safe_api_call(self, func, *args, max_retries=3, **kwargs):
        """
        安全的API调用，带重试和指数退避

        Args:
            func: 接收client作为第一参数的函数

        Returns:
            (success: bool, result: any)
        """
        for attempt in range(max_retries):
            try:
                client = self._get_client()
                result = func(client, *args, **kwargs)
                return True, result
            except Exception as e:
                error_name = type(e).__name__
                if 'Timeout' in error_name:
                    logger.warning(
                        f"IPFS API超时 (尝试 {attempt + 1}/{max_retries})"
                    )
                elif 'Connection' in error_name:
                    logger.warning(
                        f"IPFS连接丢失 (尝试 {attempt + 1}/{max_retries})"
                    )
                    try:
                        self._reconnect()
                    except Exception:
                        pass
                else:
                    logger.error(f"IPFS API错误: {error_name}: {e}")

                if attempt == max_retries - 1:
                    return False, None

                time.sleep(min(2 ** attempt, 10))

        return False, None

    # ==================== 核心爬行 ====================

    async def crawl_network(self, seed_peers: List[str] = None) -> Dict:
        """
        广度优先爬行DHT网络

        Args:
            seed_peers: 种子节点列表，空则用引导节点
        Returns:
            爬行统计
        """
        if self._is_crawling:
            logger.warning("爬行任务已在运行")
            return {'status': 'already_running'}

        self._is_crawling = True
        self._crawl_queue = asyncio.Queue()
        self._visited_peers = set()
        crawl_start = time.time()

        logger.info(f"开始DHT网络爬行，最大深度: {self.crawl_depth}")

        try:
            # 初始化种子
            seeds = seed_peers or await self._get_seed_peers()
            for peer_id in seeds:
                await self._crawl_queue.put((peer_id, 0))

            # 并发爬行
            workers = [
                asyncio.create_task(self._crawl_worker(i))
                for i in range(self.crawl_concurrency)
            ]
            await self._crawl_queue.join()
            for w in workers:
                w.cancel()

            elapsed = time.time() - crawl_start
            self._crawl_stats['crawl_rounds'] += 1
            self._crawl_stats['last_crawl_time'] = datetime.utcnow().isoformat()

            stats = {
                'status': 'completed',
                'total_peers_discovered': len(self.peers),
                'new_peers_this_round': len(self._visited_peers),
                'providing_peers': sum(
                    1 for p in self.peers.values()
                    if p.status == PeerStatus.PROVIDING
                ),
                'unreachable_peers': sum(
                    1 for p in self.peers.values()
                    if p.status == PeerStatus.UNREACHABLE
                ),
                'elapsed_seconds': round(elapsed, 2),
                'crawl_depth': self.crawl_depth
            }
            logger.info(f"DHT爬行完成: {stats}")
            return stats

        except Exception as e:
            logger.error(f"DHT爬行异常: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}
        finally:
            self._is_crawling = False

    async def _crawl_worker(self, worker_id: int):
        """爬行工作协程"""
        while True:
            try:
                peer_id, depth = await asyncio.wait_for(
                    self._crawl_queue.get(), timeout=30
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                break

            try:
                if peer_id in self._visited_peers or depth > self.crawl_depth:
                    self._crawl_queue.task_done()
                    continue
                if len(self.peers) >= self.max_peers:
                    self._crawl_queue.task_done()
                    continue

                self._visited_peers.add(peer_id)

                # 探测节点
                peer_info = await self._probe_peer(peer_id)
                if peer_info is None:
                    self._crawl_queue.task_done()
                    continue

                is_new = peer_id not in self.peers
                self.peers[peer_id] = peer_info

                if is_new:
                    self._crawl_stats['total_discovered'] += 1
                    await self._trigger_callbacks(
                        self._on_new_peer_callbacks, peer_info
                    )

                # 获取邻居
                neighbors = await self._get_peer_neighbors(peer_id)
                for neighbor_id in neighbors:
                    if neighbor_id not in self._visited_peers:
                        await self._crawl_queue.put((neighbor_id, depth + 1))

                logger.debug(
                    f"Worker-{worker_id}: {peer_id[:16]}... "
                    f"深度={depth}, {len(neighbors)}个邻居"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker-{worker_id} 错误: {e}")
            finally:
                self._crawl_queue.task_done()

    async def _get_seed_peers(self) -> List[str]:
        """获取种子节点"""
        seed_peers = []

        # 从引导节点提取Peer ID
        for addr in self.BOOTSTRAP_PEERS:
            parts = addr.split('/p2p/')
            if len(parts) == 2:
                seed_peers.append(parts[1])

        # 从已连接节点获取
        success, result = self._safe_api_call(
            lambda c: c.swarm.peers()
        )
        if success and result:
            peers_list = result.get('Peers', []) if isinstance(result, dict) else []
            for peer in peers_list:
                pid = peer.get('Peer', '')
                if pid and pid not in seed_peers:
                    seed_peers.append(pid)

        logger.info(f"获取到 {len(seed_peers)} 个种子节点")
        return seed_peers

    async def _probe_peer(self, peer_id: str) -> Optional[PeerInfo]:
        """深度探测单个节点"""
        existing = self.peers.get(peer_id)
        if existing and not existing.is_stale(max_age_hours=1):
            existing.update_last_seen()
            return existing

        peer_info = PeerInfo(peer_id=peer_id)

        # 查找节点地址
        success, result = self._safe_api_call(
            lambda c: c.dht.findpeer(peer_id), max_retries=2
        )
        if success and result:
            addresses = self._extract_addresses(result)
            peer_info.addresses = addresses
            if addresses:
                peer_info.status = PeerStatus.DISCOVERED
                self._crawl_stats['total_connected'] += 1
            else:
                peer_info.status = PeerStatus.UNREACHABLE
                self._crawl_stats['total_failed'] += 1
        else:
            peer_info.status = PeerStatus.UNREACHABLE
            peer_info.connection_failures += 1
            self._crawl_stats['total_failed'] += 1

        # 获取节点ID信息
        success, result = self._safe_api_call(
            lambda c: c.id(peer_id), max_retries=1
        )
        if success and result:
            peer_info.agent_version = result.get('AgentVersion')
            peer_info.protocols = result.get('Protocols', [])
            if not peer_info.addresses:
                peer_info.addresses = result.get('Addresses', [])

        # 测量延迟
        peer_info.latency_ms = await self._measure_latency(peer_id)

        return peer_info

    async def _get_peer_neighbors(self, peer_id: str) -> List[str]:
        """获取节点的DHT路由表邻居"""
        neighbors = set()

        # 方法1: dht query
        success, result = self._safe_api_call(
            lambda c: c.dht.query(peer_id), max_retries=1
        )
        if success and result:
            neighbors.update(self._extract_peer_ids(result))

        # 方法2: swarm peers
        success, result = self._safe_api_call(lambda c: c.swarm.peers())
        if success and result:
            peers_list = result.get('Peers', []) if isinstance(result, dict) else []
            for peer in peers_list:
                pid = peer.get('Peer', '')
                if pid:
                    neighbors.add(pid)

        neighbors.discard(peer_id)
        return list(neighbors)

    async def _measure_latency(self, peer_id: str) -> Optional[float]:
        """测量延迟（毫秒）"""
        success, result = self._safe_api_call(
            lambda c: c.ping(peer_id, count=1), max_retries=1
        )
        if success and result:
            entries = result if isinstance(result, list) else [result]
            for entry in entries:
                if isinstance(entry, dict):
                    t = entry.get('Time', 0)
                    if t > 0:
                        return t / 1_000_000
        return None

    # ==================== CID提供者发现 ====================

    async def find_providers(
        self, cid: str, num_providers: int = 20
    ) -> CIDRecord:
        """查找CID的所有提供者"""
        record = self.cid_records.get(cid, CIDRecord(cid=cid))

        success, result = self._safe_api_call(
            lambda c: c.dht.findprovs(cid, num_providers=num_providers),
            max_retries=3
        )
        if not success:
            logger.warning(f"无法查找CID提供者: {cid}")
            return record

        provider_ids = self._extract_provider_ids(result)
        previous_count = len(record.providers)

        for pid in provider_ids:
            record.add_provider(pid)
            if pid not in self.peers:
                self.peers[pid] = PeerInfo(
                    peer_id=pid,
                    status=PeerStatus.PROVIDING,
                    provided_cids={cid}
                )
            else:
                self.peers[pid].status = PeerStatus.PROVIDING
                self.peers[pid].provided_cids.add(cid)
                self.peers[pid].update_last_seen()

        new_count = len(record.providers)
        if new_count > previous_count:
            logger.info(f"CID {cid[:16]}... 提供者: {previous_count} -> {new_count}")
            await self._trigger_callbacks(
                self._on_provider_change_callbacks, cid, record
            )

        self.cid_records[cid] = record
        return record

    async def find_providers_deep(self, cid: str) -> CIDRecord:
        """
        深度查找CID提供者
        通过提供者的邻居进一步搜索
        """
        record = await self.find_providers(cid, num_providers=50)
        first_round = set(record.providers)

        for provider_id in first_round:
            neighbors = await self._get_peer_neighbors(provider_id)
            for neighbor in neighbors[:5]:
                success, result = self._safe_api_call(
                    lambda c: c.dht.findprovs(cid, num_providers=5),
                    max_retries=1
                )
                if success:
                    for pid in self._extract_provider_ids(result):
                        record.add_provider(pid)

        logger.info(
            f"CID {cid[:16]}... 深度搜索完成，总提供者: {len(record.providers)}"
        )
        self.cid_records[cid] = record
        return record

    # ==================== 持续监控 ====================

    async def watch_cid(self, cid: str):
        """添加CID到监控列表"""
        self.watched_cids.add(cid)
        logger.info(f"已添加CID监控: {cid}")

    async def unwatch_cid(self, cid: str):
        self.watched_cids.discard(cid)

    async def start_continuous_monitoring(
        self,
        crawl_interval: int = 300,
        provider_check_interval: int = 60
    ):
        """启动持续监控"""
        logger.info("启动DHT持续监控...")
        tasks = [
            asyncio.create_task(self._periodic_crawl(crawl_interval)),
            asyncio.create_task(
                self._periodic_provider_check(provider_check_interval)
            ),
            asyncio.create_task(self._cleanup_stale_peers()),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("DHT监控已停止")
            for t in tasks:
                t.cancel()

    async def _periodic_crawl(self, interval: int):
        while True:
            try:
                await self.crawl_network()
            except Exception as e:
                logger.error(f"定期爬行失败: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _periodic_provider_check(self, interval: int):
        while True:
            for cid in list(self.watched_cids):
                try:
                    await self.find_providers(cid)
                except Exception as e:
                    logger.error(f"检查CID {cid} 失败: {e}")
                await asyncio.sleep(2)
            await asyncio.sleep(interval)

    async def _cleanup_stale_peers(self, interval: int = 3600):
        while True:
            await asyncio.sleep(interval)
            stale = 0
            for pid in list(self.peers.keys()):
                if self.peers[pid].is_stale(max_age_hours=48):
                    self.peers[pid].status = PeerStatus.UNREACHABLE
                    stale += 1
            if stale:
                logger.info(f"标记 {stale} 个过期节点")

    # ==================== 回调 ====================

    def on_new_peer(self, callback):
        self._on_new_peer_callbacks.append(callback)

    def on_new_cid(self, callback):
        self._on_new_cid_callbacks.append(callback)

    def on_provider_change(self, callback):
        self._on_provider_change_callbacks.append(callback)

    async def _trigger_callbacks(self, callbacks, *args):
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(*args)
                else:
                    cb(*args)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    # ==================== 解析辅助 ====================

    def _extract_addresses(self, response) -> List[str]:
        addresses = []
        try:
            entries = response if isinstance(response, list) else [response]
            for entry in entries:
                if isinstance(entry, dict):
                    for resp in entry.get('Responses', []):
                        addresses.extend(resp.get('Addrs', []))
        except (KeyError, TypeError) as e:
            logger.debug(f"解析地址出错: {e}")
        return addresses

    def _extract_peer_ids(self, response) -> List[str]:
        peer_ids = []
        try:
            entries = response if isinstance(response, list) else [response]
            for entry in entries:
                if isinstance(entry, dict):
                    for resp in entry.get('Responses', []):
                        pid = resp.get('ID', '')
                        if pid:
                            peer_ids.append(pid)
                    pid = entry.get('ID', '')
                    if pid:
                        peer_ids.append(pid)
        except (KeyError, TypeError) as e:
            logger.debug(f"解析节点ID出错: {e}")
        return list(set(peer_ids))

    def _extract_provider_ids(self, response) -> List[str]:
        provider_ids = []
        try:
            entries = response if isinstance(response, list) else [response]
            for entry in entries:
                if isinstance(entry, dict):
                    for resp in entry.get('Responses', []):
                        pid = resp.get('ID', '')
                        if pid:
                            provider_ids.append(pid)
        except (KeyError, TypeError) as e:
            logger.debug(f"解析提供者出错: {e}")
        return list(set(provider_ids))

    # ==================== 统计与导出 ====================

    def get_statistics(self) -> dict:
        status_counts = defaultdict(int)
        for peer in self.peers.values():
            status_counts[peer.status.value] += 1

        return {
            'total_peers': len(self.peers),
            'peer_status_distribution': dict(status_counts),
            'total_cids_tracked': len(self.cid_records),
            'watched_cids': len(self.watched_cids),
            'crawl_stats': self._crawl_stats,
            'active_peers': sum(
                1 for p in self.peers.values()
                if not p.is_stale(max_age_hours=1)
            )
        }

    def get_providing_peers(self) -> List[PeerInfo]:
        return [
            p for p in self.peers.values()
            if p.status == PeerStatus.PROVIDING
        ]

    def get_peer_by_cid(self, cid: str) -> List[PeerInfo]:
        record = self.cid_records.get(cid)
        if not record:
            return []
        return [self.peers[pid] for pid in record.providers if pid in self.peers]

    def export_network_graph(self) -> dict:
        """导出网络拓扑图数据（给前端ECharts用）"""
        nodes = []
        edges = []

        for pid, info in self.peers.items():
            nodes.append({
                'id': pid[:16],
                'full_id': pid,
                'status': info.status.value,
                'cid_count': len(info.provided_cids),
                'latency': info.latency_ms
            })

        for cid, record in self.cid_records.items():
            providers = list(record.providers)
            for i in range(len(providers)):
                for j in range(i + 1, len(providers)):
                    edges.append({
                        'source': providers[i][:16],
                        'target': providers[j][:16],
                        'cid': cid[:16],
                        'type': 'co-provide'
                    })

        return {'nodes': nodes, 'edges': edges}

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None