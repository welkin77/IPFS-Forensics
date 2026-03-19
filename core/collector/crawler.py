"""
多源情报嗅探引擎
位置: core/collector/crawler.py
对应设计方案 3.1

职责：统一调度所有信源的扫描，管理去重和状态
不再自己写采集逻辑，而是组合调用子模块
"""

import time
import logging
from typing import List, Dict, Set, Optional

from core.collector.dht_sniffer import DHTSniffer
from core.collector.forum_scanner import ForumScanner

logger = logging.getLogger(__name__)


class IntelligenceCrawler:
    """
    多源情报嗅探引擎

    单例使用：通过 get_instance() 获取全局唯一实例
    确保跨请求去重状态不丢失
    """

    _instance: Optional['IntelligenceCrawler'] = None

    @classmethod
    def get_instance(cls) -> 'IntelligenceCrawler':
        """单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # 子模块
        self._dht = DHTSniffer()
        self._forum = ForumScanner()

        # 全局去重集合（跨轮次）
        self._known_cids: Set[str] = set()

        # 状态追踪
        self._is_scanning: bool = False
        self._scan_count: int = 0
        self._last_scan_time: str = ""
        self._last_scan_result: int = 0

    def load_known_cids(self, existing_cids: List[str]):
        """从数据库加载已有CID，启动时调用一次"""
        self._known_cids.update(existing_cids)
        logger.info(f"已加载 {len(self._known_cids)} 个历史CID到去重集合")

    def scan_network(self, keywords: List[str] = None) -> List[Dict]:
        """
        执行一次全网嗅探，只返回新发现的CID

        流程：
        1. 论坛/Reddit公开信源扫描
        2. 本地IPFS节点DHT嗅探
        3. 跨轮次去重
        4. 返回新线索
        """
        self._is_scanning = True
        self._scan_count += 1
        logger.info("启动多源情报嗅探引擎...")

        all_clues = []

        # 信源1: 公开论坛 + Reddit
        try:
            forum_clues = self._forum.scan_all()
            all_clues.extend(forum_clues)
        except Exception as e:
            logger.error(f"论坛扫描异常: {e}")

        # 信源2: 本地IPFS DHT/Bitswap嗅探
        try:
            dht_clues = self._dht.sniff_wantlists(max_peers=15)
            all_clues.extend(dht_clues)
        except Exception as e:
            logger.error(f"DHT嗅探异常: {e}")

        # 去重：本轮内 + 跨轮次
        new_clues = self._deduplicate(all_clues)

        # 更新状态
        self._is_scanning = False
        self._last_scan_time = time.strftime('%Y-%m-%d %H:%M:%S')
        self._last_scan_result = len(new_clues)

        if new_clues:
            logger.info(
                f"本次扫描完成，发现 {len(new_clues)} 条全新CID线索"
            )
        else:
            logger.info(
                f"本次扫描完成，未发现新线索"
                f"（已知 {len(self._known_cids)} 个CID）"
            )

        return new_clues

    def _deduplicate(self, clues: List[Dict]) -> List[Dict]:
        """双层去重：本轮内去重 + 跨轮次去重"""
        new_clues = []
        seen_this_round: Set[str] = set()

        for clue in clues:
            cid = clue.get('cid', '')
            if not cid:
                continue

            # 本轮去重
            if cid in seen_this_round:
                continue
            seen_this_round.add(cid)

            # 跨轮次去重
            if cid in self._known_cids:
                continue

            self._known_cids.add(cid)
            new_clues.append(clue)

        return new_clues

    def get_status(self) -> Dict:
        """获取引擎状态（给前端展示）"""
        return {
            'is_scanning': self._is_scanning,
            'scan_count': self._scan_count,
            'known_cids_count': len(self._known_cids),
            'last_scan_time': self._last_scan_time,
            'last_scan_result_count': self._last_scan_result,
            'ipfs_node_available': self._dht.is_available(),
            'connected_peers': len(self._dht.get_connected_peers()) if self._dht.is_available() else 0,
        }

    def find_providers(self, cid: str) -> List[str]:
        """查找CID的提供者节点（代理给DHT模块）"""
        return self._dht.find_providers(cid)

    def get_node_info(self) -> Optional[Dict]:
        """获取本地IPFS节点信息"""
        return self._dht.get_node_info()