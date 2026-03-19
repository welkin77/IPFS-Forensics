import time
import requests
import re
import random
from typing import List, Dict, Set, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

# ★ 可选导入：没装依赖时不影响基础功能
try:
    from core.collector.dht_probe import DHTProbe
    HAS_DHT_PROBE = True
except ImportError:
    HAS_DHT_PROBE = False

try:
    from core.collector.osint_monitor import CIDExtractor
    HAS_OSINT = True
except ImportError:
    HAS_OSINT = False


class IntelligenceCrawler:
    """
    混合情报嗅探引擎 v3
    
    基础能力（无额外依赖）：
      - IPFS 官方论坛采集
      - Reddit 公开搜索
      - 本地 IPFS 节点 Bitswap 嗅探
    
    增强能力（有依赖时自动启用）：
      - DHT 深度爬行和提供者追踪（需要 ipfshttpclient）
      - 更精准的 CID 提取（使用 osint_monitor 的正则库）
    """

    def __init__(self):
        # CID正则：优先用 osint_monitor 的（更全面），否则用自带的
        if HAS_OSINT:
            self.cid_pattern = CIDExtractor.CIDV0_PATTERN
            self.cid_v1_pattern = CIDExtractor.CIDV1_PATTERN
            logger.info("[引擎增强] 已加载 OSINT 模块的 CID 提取器")
        else:
            self.cid_pattern = re.compile(r'(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z0-9]{55})')
            self.cid_v1_pattern = None

        # DHT深度探测器（可选）
        self._dht_probe: Optional['DHTProbe'] = None
        if HAS_DHT_PROBE:
            try:
                self._dht_probe = DHTProbe()
                logger.info("[引擎增强] 已加载 DHT 深度嗅探模块")
            except Exception as e:
                logger.warning(f"DHT 探测器初始化失败（降级到基础模式）: {e}")
                self._dht_probe = None

        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]

        # 跨轮次去重
        self._known_cids: Set[str] = set()

        # 增量游标
        self._discourse_last_post_id: int = 0
        self._reddit_last_name: str = ""

    def _get_random_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'application/json, text/html, application/xhtml+xml, */*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }

    def _extract_cids_from_text(self, text: str) -> List[str]:
        """
        从文本中提取CID
        优先使用 OSINT 模块的提取器（覆盖更多格式），否则用基础正则
        """
        if not text:
            return []

        if HAS_OSINT:
            return CIDExtractor.extract_cids(text)
        else:
            return self.cid_pattern.findall(text)

    def load_known_cids(self, existing_cids: List[str]):
        """从数据库加载已有CID，启动时调用一次"""
        self._known_cids.update(existing_cids)
        logger.info(f"已加载 {len(self._known_cids)} 个历史 CID 到去重集合")

    def scan_network(self, keywords: List[str] = None) -> List[Dict]:
        """执行一次全网嗅探周期，只返回新发现的CID"""
        discovered_clues = []
        logger.info("启动多源情报嗅探引擎...")

        # ---------------------------------------------------------
        # 1. IPFS 官方论坛 (增量采集)
        # ---------------------------------------------------------
        try:
            discourse_url = "https://discuss.ipfs.tech/posts.json"
            res = requests.get(discourse_url, headers=self._get_random_headers(), timeout=10)
            if res.status_code == 200:
                posts = res.json().get('latest_posts', [])
                max_post_id = self._discourse_last_post_id

                for post in posts:
                    post_id = post.get('id', 0)
                    if post_id <= self._discourse_last_post_id:
                        continue

                    max_post_id = max(max_post_id, post_id)
                    text = post.get('raw', '')
                    found_cids = self._extract_cids_from_text(text)
                    for cid in found_cids:
                        discovered_clues.append({
                            "cid": cid,
                            "source": f"IPFS_Official_Forum (User:{post.get('username')})",
                            "keyword": "开发者社区"
                        })

                if max_post_id > self._discourse_last_post_id:
                    self._discourse_last_post_id = max_post_id
            else:
                logger.debug(f"官方论坛返回状态码: {res.status_code}")
        except Exception as e:
            logger.warning(f"官方论坛信源获取失败: {e}")

        # ---------------------------------------------------------
        # 2. Reddit (增量采集)
        # ---------------------------------------------------------
        try:
            reddit_url = "https://www.reddit.com/search.json?q=ipfs+OR+bafy&sort=new&limit=25"
            if self._reddit_last_name:
                reddit_url += f"&before={self._reddit_last_name}"

            res = requests.get(reddit_url, headers=self._get_random_headers(), timeout=10)
            if res.status_code == 200:
                data = res.json().get('data', {})
                posts = data.get('children', [])

                if posts:
                    self._reddit_last_name = posts[0]['data'].get('name', '')

                for post in posts:
                    text = post['data'].get('selftext', '') + " " + post['data'].get('title', '')
                    found_cids = self._extract_cids_from_text(text)
                    for cid in found_cids:
                        discovered_clues.append({
                            "cid": cid,
                            "source": f"Reddit (r/{post['data'].get('subreddit', 'unknown')})",
                            "keyword": "互联网公开信源"
                        })
            elif res.status_code == 429:
                logger.debug("Reddit 触发了反爬限流 (429)")
        except Exception:
            pass

        # ---------------------------------------------------------
        # 3. DHT/Swarm 嗅探（基础 + 深度增强）
        # ---------------------------------------------------------
        try:
            swarm_url = "http://127.0.0.1:5001/api/v0/swarm/peers"
            res = requests.post(swarm_url, timeout=5)

            if res.status_code == 200:
                peers = res.json().get('Peers', [])
                logger.info(f"本地 IPFS 守护进程已连接 {len(peers)} 个全球对等节点。")

                # --- 3a. 基础嗅探：Bitswap Wantlist（原有逻辑） ---
                sample_peers = random.sample(peers, min(15, len(peers))) if peers else []

                for peer in sample_peers:
                    peer_id = peer['Peer']
                    wantlist_url = f"http://127.0.0.1:5001/api/v0/bitswap/wantlist?peer={peer_id}"
                    try:
                        wl_res = requests.post(wantlist_url, timeout=3)
                        if wl_res.status_code == 200:
                            keys = wl_res.json().get('Keys') or []
                            for key_obj in keys:
                                if isinstance(key_obj, dict) and "/" in key_obj:
                                    raw_cid = key_obj["/"]
                                    if self.cid_pattern.match(raw_cid):
                                        discovered_clues.append({
                                            "cid": raw_cid,
                                            "source": f"IPFS_Bitswap_Peer ({peer_id[:8]}...)",
                                            "keyword": "P2P底层数据流"
                                        })
                    except Exception:
                        continue

                # --- 3b. ★ 增强嗅探：DHT深度爬行（有模块时自动启用） ---
                if self._dht_probe:
                    try:
                        dht_clues = self._dht_deep_scan(peers)
                        discovered_clues.extend(dht_clues)
                    except Exception as e:
                        logger.debug(f"DHT深度嗅探异常（不影响基础功能）: {e}")

        except requests.exceptions.ConnectionError:
            logger.warning("本地 IPFS Daemon 未启动，无法进行底层 DHT/Bitswap 嗅探。")
        except Exception as e:
            logger.error(f"本地 IPFS 嗅探发生未知错误: {e}")

        # ---------------------------------------------------------
        # 4. 去重：单次 + 跨轮次
        # ---------------------------------------------------------
        new_clues = []
        seen_this_round: Set[str] = set()

        for c in discovered_clues:
            cid = c['cid']
            if cid in seen_this_round:
                continue
            seen_this_round.add(cid)

            if cid in self._known_cids:
                continue

            self._known_cids.add(cid)
            new_clues.append(c)

        if new_clues:
            logger.info(f"本次雷达扫描结束，共发现 {len(new_clues)} 条全新独立 CID 线索。")
        else:
            logger.info(f"本次雷达扫描结束，未发现新线索（已知 {len(self._known_cids)} 个 CID）。")

        return new_clues

    # ==================== DHT深度嗅探（增强模块） ====================

    def _dht_deep_scan(self, peers: list) -> List[Dict]:
        """
        利用 DHTProbe 进行深度嗅探
        只在 dht_probe.py 可用时被调用
        """
        if not self._dht_probe:
            return []

        clues = []

        # 从已连接节点中随机取几个，查询它们提供的内容
        sample = random.sample(peers, min(5, len(peers))) if peers else []

        for peer in sample:
            peer_id = peer['Peer']
            try:
                # 查找该节点的邻居节点（扩展发现范围）
                success, result = self._dht_probe._safe_api_call(
                    lambda c: c.dht.query(peer_id), max_retries=1
                )
                if success and result:
                    neighbor_ids = self._dht_probe._extract_peer_ids(result)

                    # 记录发现的新节点
                    for nid in neighbor_ids[:3]:
                        if nid not in self._dht_probe.peers:
                            from core.collector.dht_probe import PeerInfo, PeerStatus
                            self._dht_probe.peers[nid] = PeerInfo(
                                peer_id=nid,
                                status=PeerStatus.DISCOVERED
                            )

                    if neighbor_ids:
                        logger.debug(
                            f"[DHT增强] 节点 {peer_id[:8]}... "
                            f"发现 {len(neighbor_ids)} 个邻居"
                        )

            except Exception:
                continue

        # 如果有正在监控的CID，检查提供者变化
        for cid in list(self._dht_probe.watched_cids)[:5]:
            try:
                success, result = self._dht_probe._safe_api_call(
                    lambda c: c.dht.findprovs(cid, num_providers=10),
                    max_retries=1
                )
                if success:
                    providers = self._dht_probe._extract_provider_ids(result)
                    for pid in providers:
                        clues.append({
                            "cid": cid,
                            "source": f"DHT_Deep_Scan (Provider:{pid[:8]}...)",
                            "keyword": "DHT深度嗅探"
                        })
            except Exception:
                continue

        if clues:
            logger.info(f"[DHT增强] 深度嗅探发现 {len(clues)} 条线索")

        return clues

    # ==================== 对外接口 ====================

    def get_engine_status(self) -> Dict:
        """获取引擎状态（给前端展示）"""
        return {
            "known_cids": len(self._known_cids),
            "discourse_cursor": self._discourse_last_post_id,
            "reddit_cursor": self._reddit_last_name[:20] if self._reddit_last_name else "无",
            "dht_enhanced": self._dht_probe is not None,
            "osint_enhanced": HAS_OSINT,
            "dht_peers_known": len(self._dht_probe.peers) if self._dht_probe else 0,
        }

    def watch_cid(self, cid: str):
        """添加CID到DHT深度监控（如果DHT模块可用）"""
        if self._dht_probe:
            self._dht_probe.watched_cids.add(cid)
            logger.info(f"[DHT增强] 已添加 CID 到深度监控: {cid[:20]}...")
        else:
            logger.debug(f"DHT模块不可用，跳过深度监控: {cid[:20]}...")

    def close(self):
        """关闭资源"""
        if self._dht_probe:
            self._dht_probe.close()