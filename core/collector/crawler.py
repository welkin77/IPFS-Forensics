import time
import requests
import re
import random
from typing import List, Dict
from utils.logger import setup_logger

logger = setup_logger(__name__)

class IntelligenceCrawler:
    """真实的混合情报嗅探引擎 (修复版：防御空值注入，增加高可用信源)"""

    def __init__(self):
        # 匹配 IPFS CID 的正则表达式 (CIDv0 以 Qm 开头，CIDv1 以 bafy 开头)
        self.cid_pattern = re.compile(r'(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z0-9]{55})')
        
        # 真实的现代浏览器 UA 池，防止被反爬系统拦截
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        ]

    def _get_random_headers(self) -> Dict[str, str]:
        """获取随机请求头"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'application/json, text/html, application/xhtml+xml, */*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }

    def scan_network(self, keywords: List[str] = None) -> List[Dict]:
        """执行一次全网嗅探周期"""
        discovered_clues = []
        logger.info("启动多源情报嗅探引擎...")

        # ---------------------------------------------------------
        # 1. 真实采集：公开信源 - IPFS 官方论坛 (高可靠，无需鉴权)
        # ---------------------------------------------------------
        try:
            # Discourse 论坛自带的 .json API 极其稳定
            discourse_url = "https://discuss.ipfs.tech/posts.json"
            res = requests.get(discourse_url, headers=self._get_random_headers(), timeout=10)
            if res.status_code == 200:
                posts = res.json().get('latest_posts', [])
                for post in posts:
                    text = post.get('raw', '') # 获取帖子原始文本
                    found_cids = self.cid_pattern.findall(text)
                    for cid in found_cids:
                        discovered_clues.append({
                            "cid": cid,
                            "source": f"IPFS_Official_Forum (User:{post.get('username')})",
                            "keyword": "开发者社区"
                        })
            else:
                logger.debug(f"官方论坛返回状态码: {res.status_code}")
        except Exception as e:
            logger.warning(f"官方论坛信源获取失败: {e}")

        # ---------------------------------------------------------
        # 2. 真实采集：公开信源 - 广域 Reddit
        # ---------------------------------------------------------
        try:
            reddit_url = "https://www.reddit.com/search.json?q=ipfs+OR+bafy&sort=new&limit=10"
            res = requests.get(reddit_url, headers=self._get_random_headers(), timeout=10)
            if res.status_code == 200:
                posts = res.json().get('data', {}).get('children', [])
                for post in posts:
                    text = post['data'].get('selftext', '') + " " + post['data'].get('title', '')
                    found_cids = self.cid_pattern.findall(text)
                    for cid in found_cids:
                        discovered_clues.append({
                            "cid": cid,
                            "source": f"Reddit (r/{post['data'].get('subreddit', 'unknown')})",
                            "keyword": "互联网公开信源"
                        })
            elif res.status_code == 429:
                logger.debug("Reddit 触发了反爬限流 (429 Too Many Requests)")
        except Exception as e:
            pass # 忽略 Reddit 报错，避免刷屏

        # ---------------------------------------------------------
        # 3. 真实采集：DHT/Swarm 底层嗅探 (利用 Bitswap 协议)
        # ---------------------------------------------------------
        try:
            # 步骤 A: 获取当前 IPFS 节点连接的全球对等节点
            swarm_url = "http://127.0.0.1:5001/api/v0/swarm/peers"
            res = requests.post(swarm_url, timeout=5)
            
            if res.status_code == 200:
                peers = res.json().get('Peers', [])
                logger.info(f"本地 IPFS 守护进程已连接 {len(peers)} 个全球对等节点。")
                
                # 随机抽取部分节点进行深层嗅探
                sample_peers = random.sample(peers, min(15, len(peers))) if peers else []
                
                for peer in sample_peers:
                    peer_id = peer['Peer']
                    # 步骤 B: 真实取证级嗅探 -> 查询该节点当前的 Bitswap Wantlist
                    wantlist_url = f"http://127.0.0.1:5001/api/v0/bitswap/wantlist?peer={peer_id}"
                    wl_res = requests.post(wantlist_url, timeout=3)
                    
                    if wl_res.status_code == 200:
                        data = wl_res.json()
                        # 【重要修复】：如果节点当前没有请求，'Keys' 的值是 None，使用 `or []` 防御 NoneType 错误
                        keys = data.get('Keys') or []  
                        
                        for key_obj in keys:
                            if isinstance(key_obj, dict) and "/" in key_obj:
                                raw_cid = key_obj["/"]
                                if self.cid_pattern.match(raw_cid):
                                    discovered_clues.append({
                                        "cid": raw_cid,
                                        "source": f"IPFS_Bitswap_Peer ({peer_id[:8]}...)",
                                        "keyword": "P2P底层数据流"
                                    })
        except requests.exceptions.ConnectionError:
            logger.warning("本地 IPFS Daemon 未启动，无法进行底层 DHT/Bitswap 嗅探 (请启动 IPFS Desktop)。")
        except Exception as e:
            logger.error(f"本地 IPFS 嗅探发生未知错误: {e}")

        # ---------------------------------------------------------
        # 4. 数据清洗与去重
        # ---------------------------------------------------------
        unique_clues = []
        seen = set()
        for c in discovered_clues:
            if c['cid'] not in seen:
                unique_clues.append(c)
                seen.add(c['cid'])

        if unique_clues:
            logger.info(f"本次雷达扫描结束，共发现 {len(unique_clues)} 条独立真实 CID 线索。")
        else:
            logger.info("本次雷达扫描未捕获到新线索，等待下一次周期...")
            
        return unique_clues