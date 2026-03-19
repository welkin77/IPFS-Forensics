"""
公开论坛/信源扫描模块
位置: core/collector/forum_scanner.py
对应设计方案 3.1.3

职责：从公开信源（IPFS论坛、Reddit等）中提取CID线索
每个信源是一个独立方法，方便扩展新信源
"""

import re
import random
import logging
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)


class ForumScanner:
    """公开信源CID扫描器"""

    # CID正则
    CID_V0 = re.compile(r'\bQm[1-9A-HJ-NP-Za-km-z]{44}\b')
    CID_V1 = re.compile(r'\bbafy[a-z2-7]{55,}\b')

    # IPFS URL中的CID
    CID_URL = re.compile(
        r'(?:https?://[a-zA-Z0-9.-]+)?/ipfs/'
        r'(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z2-7]{55,})'
    )

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]

    def __init__(self):
        # 增量游标：记录上次扫描位置，避免重复
        self._discourse_last_post_id: int = 0
        self._reddit_last_name: str = ""

    def _random_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    def extract_cids(self, text: str) -> List[str]:
        """从文本中提取所有CID（去重）"""
        if not text:
            return []
        cids = set()
        cids.update(self.CID_V0.findall(text))
        cids.update(self.CID_V1.findall(text))
        for match in self.CID_URL.finditer(text):
            cids.add(match.group(1))
        return list(cids)

    def scan_ipfs_forum(self) -> List[Dict]:
        """
        扫描IPFS官方论坛 (discuss.ipfs.tech)
        Discourse论坛自带 .json API，极其稳定

        Returns:
            [{'cid': '...', 'source': '...', 'keyword': '...'}, ...]
        """
        clues = []
        try:
            url = "https://discuss.ipfs.tech/posts.json"
            resp = requests.get(url, headers=self._random_headers(), timeout=10)

            if resp.status_code != 200:
                logger.debug(f"IPFS论坛返回: {resp.status_code}")
                return clues

            posts = resp.json().get('latest_posts', [])
            max_id = self._discourse_last_post_id

            for post in posts:
                post_id = post.get('id', 0)

                # 增量：跳过已扫描的帖子
                if post_id <= self._discourse_last_post_id:
                    continue

                max_id = max(max_id, post_id)
                text = post.get('raw', '')
                username = post.get('username', 'unknown')

                for cid in self.extract_cids(text):
                    clues.append({
                        'cid': cid,
                        'source': f"IPFS_Official_Forum (User:{username})",
                        'keyword': '开发者社区'
                    })

            if max_id > self._discourse_last_post_id:
                self._discourse_last_post_id = max_id

        except Exception as e:
            logger.warning(f"IPFS论坛扫描失败: {e}")

        return clues

    def scan_reddit(self, subreddits: List[str] = None) -> List[Dict]:
        """
        扫描Reddit中的IPFS相关帖子

        Args:
            subreddits: 要搜索的子版块列表

        Returns:
            [{'cid': '...', 'source': '...', 'keyword': '...'}, ...]
        """
        clues = []

        try:
            url = "https://www.reddit.com/search.json"
            params = {
                'q': 'ipfs OR bafy OR "Qm"',
                'sort': 'new',
                'limit': 25,
            }
            if self._reddit_last_name:
                params['before'] = self._reddit_last_name

            resp = requests.get(
                url, params=params,
                headers=self._random_headers(),
                timeout=10
            )

            if resp.status_code == 429:
                logger.debug("Reddit限流(429)")
                return clues

            if resp.status_code != 200:
                logger.debug(f"Reddit返回: {resp.status_code}")
                return clues

            data = resp.json().get('data', {})
            posts = data.get('children', [])

            # 更新游标
            if posts:
                self._reddit_last_name = posts[0]['data'].get('name', '')

            for post_data in posts:
                post = post_data.get('data', {})
                text = (
                    f"{post.get('title', '')} "
                    f"{post.get('selftext', '')} "
                    f"{post.get('url', '')}"
                )
                subreddit = post.get('subreddit', 'unknown')

                for cid in self.extract_cids(text):
                    clues.append({
                        'cid': cid,
                        'source': f"Reddit (r/{subreddit})",
                        'keyword': '互联网公开信源'
                    })

        except Exception as e:
            logger.debug(f"Reddit扫描失败: {e}")

        return clues

    def scan_all(self) -> List[Dict]:
        """执行所有信源扫描"""
        clues = []
        clues.extend(self.scan_ipfs_forum())
        clues.extend(self.scan_reddit())
        return clues