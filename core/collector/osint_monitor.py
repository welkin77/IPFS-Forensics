"""
公开信源监控模块 (OSINT Monitor)
位置: core/collector/osint_monitor.py

功能：监控Telegram、Twitter/X、Reddit、暗网论坛中分享的IPFS链接
与现有 core/collector/ 下的网关监控模块并列
"""

import re
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
from collections import defaultdict
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================

class SourcePlatform(Enum):
    TELEGRAM = "telegram"
    TWITTER = "twitter"
    REDDIT = "reddit"
    DARKWEB = "darkweb"
    UNKNOWN = "unknown"


@dataclass
class CIDMention:
    """CID被提及的记录"""
    cid: str
    platform: SourcePlatform
    source_url: str
    author_id: str
    author_name: str = ""
    message_text: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    context: Dict = field(default_factory=dict)
    risk_score: float = 0.0
    is_processed: bool = False

    def to_dict(self) -> dict:
        return {
            'cid': self.cid,
            'platform': self.platform.value,
            'source_url': self.source_url,
            'author_id': self.author_id,
            'author_name': self.author_name,
            'message_text': self.message_text[:500],
            'timestamp': self.timestamp.isoformat(),
            'context': self.context,
            'risk_score': self.risk_score,
            'is_processed': self.is_processed
        }


# ==================== CID提取器 ====================

class CIDExtractor:
    """从文本中提取IPFS CID"""

    CIDV0_PATTERN = re.compile(r'\bQm[1-9A-HJ-NP-Za-km-z]{44}\b')
    CIDV1_PATTERN = re.compile(r'\bbafy[a-z2-7]{55,}\b')

    IPFS_URL_PATTERNS = [
        re.compile(
            r'https?://[a-zA-Z0-9.-]+/ipfs/'
            r'(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z2-7]{55,})'
        ),
        re.compile(
            r'ipfs://(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z2-7]{55,})'
        ),
        re.compile(
            r'/ipfs/(Qm[1-9A-HJ-NP-Za-km-z]{44}|bafy[a-z2-7]{55,})'
        ),
    ]

    RISK_KEYWORDS_ZH = [
        '破解', '色情', '赌博', '诈骗', '毒品', '枪支', '炸弹',
        '偷拍', '身份证', '银行卡', '数据库', '泄露', '黑客',
        '翻墙', '暗网', '洗钱', '传销', '套路贷'
    ]

    RISK_KEYWORDS_EN = [
        'crack', 'porn', 'xxx', 'gambling', 'scam', 'drug', 'weapon',
        'leak', 'hack', 'exploit', 'malware', 'ransomware',
        'stolen', 'fraud', 'illegal', 'darknet', 'tor'
    ]

    @classmethod
    def extract_cids(cls, text: str) -> List[str]:
        if not text:
            return []
        cids = set()
        for match in cls.CIDV0_PATTERN.finditer(text):
            cids.add(match.group())
        for match in cls.CIDV1_PATTERN.finditer(text):
            cids.add(match.group())
        for pattern in cls.IPFS_URL_PATTERNS:
            for match in pattern.finditer(text):
                cids.add(match.group(1))
        return list(cids)

    @classmethod
    def calculate_risk_score(cls, text: str) -> float:
        if not text:
            return 0.0
        text_lower = text.lower()
        hit_count = 0
        total = len(cls.RISK_KEYWORDS_ZH) + len(cls.RISK_KEYWORDS_EN)

        for kw in cls.RISK_KEYWORDS_ZH:
            if kw in text:
                hit_count += 1
        for kw in cls.RISK_KEYWORDS_EN:
            if kw in text_lower:
                hit_count += 1

        return round(min(hit_count / max(total * 0.1, 1), 1.0), 3)


# ==================== 监控基类 ====================

class BaseMonitor(ABC):
    """信源监控基类"""

    def __init__(self):
        self.mentions: List[CIDMention] = []
        self._callbacks: List[Callable] = []
        self._is_running = False
        self._stats = {
            'messages_scanned': 0,
            'cids_found': 0,
            'errors': 0,
            'last_scan_time': None
        }

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    def on_cid_found(self, callback: Callable):
        self._callbacks.append(callback)

    async def _notify_callbacks(self, mention: CIDMention):
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(mention)
                else:
                    cb(mention)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    def _record_mention(self, mention: CIDMention):
        self.mentions.append(mention)
        self._stats['cids_found'] += 1

    def get_stats(self) -> dict:
        return self._stats.copy()


# ==================== Telegram 监控 ====================

class TelegramMonitor(BaseMonitor):
    """
    Telegram群组/频道监控

    需要:
    - pip install telethon
    - Telegram API ID/Hash (https://my.telegram.org)
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_name: str = 'ipfs_monitor',
        channels: List[str] = None,
        proxy: Optional[dict] = None
    ):
        super().__init__()
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.channels = channels or []
        self.proxy = proxy
        self._client = None

    async def start(self):
        try:
            from telethon import TelegramClient, events
        except ImportError:
            logger.error("需要安装telethon: pip install telethon")
            raise ImportError("pip install telethon")

        self._is_running = True

        proxy_config = None
        if self.proxy:
            proxy_config = (
                self.proxy.get('type', 'socks5'),
                self.proxy.get('host', '127.0.0.1'),
                self.proxy.get('port', 1080)
            )

        self._client = TelegramClient(
            self.session_name, self.api_id, self.api_hash,
            proxy=proxy_config
        )
        await self._client.start()
        logger.info("Telegram客户端已启动")

        @self._client.on(events.NewMessage(chats=self.channels))
        async def handler(event):
            await self._process_message(event)

        logger.info(f"监控 {len(self.channels)} 个Telegram频道")

        # 扫描历史
        asyncio.create_task(self._scan_history())

        await self._client.run_until_disconnected()

    async def stop(self):
        self._is_running = False
        if self._client:
            await self._client.disconnect()
            logger.info("Telegram监控已停止")

    async def _process_message(self, event):
        try:
            text = event.message.text or ''
            self._stats['messages_scanned'] += 1
            cids = CIDExtractor.extract_cids(text)
            if not cids:
                return

            sender = await event.get_sender()
            sender_id = str(sender.id) if sender else 'unknown'
            sender_name = ''
            if sender:
                sender_name = (
                    getattr(sender, 'username', '') or
                    getattr(sender, 'first_name', '') or ''
                )

            chat = await event.get_chat()
            chat_title = getattr(chat, 'title', str(chat.id))

            for cid in cids:
                mention = CIDMention(
                    cid=cid,
                    platform=SourcePlatform.TELEGRAM,
                    source_url=f"https://t.me/{chat_title}/{event.message.id}",
                    author_id=sender_id,
                    author_name=sender_name,
                    message_text=text,
                    timestamp=event.message.date,
                    context={
                        'chat_id': str(chat.id),
                        'chat_title': chat_title,
                        'message_id': event.message.id,
                        'has_media': event.message.media is not None
                    },
                    risk_score=CIDExtractor.calculate_risk_score(text)
                )
                self._record_mention(mention)
                await self._notify_callbacks(mention)
                logger.info(
                    f"[TG] CID: {cid[:20]}... "
                    f"from {sender_name}@{chat_title} "
                    f"risk={mention.risk_score}"
                )
        except Exception as e:
            self._stats['errors'] += 1
            logger.error(f"处理TG消息出错: {e}", exc_info=True)

    async def _scan_history(self, limit_per_channel: int = 1000):
        for channel in self.channels:
            try:
                logger.info(f"扫描TG频道历史: {channel}")
                count = 0
                async for message in self._client.iter_messages(
                    channel, limit=limit_per_channel
                ):
                    if not self._is_running:
                        break
                    text = message.text or ''
                    cids = CIDExtractor.extract_cids(text)
                    self._stats['messages_scanned'] += 1
                    if cids:
                        sender = await message.get_sender()
                        sid = str(sender.id) if sender else 'unknown'
                        sname = getattr(sender, 'username', '') if sender else ''
                        for cid in cids:
                            mention = CIDMention(
                                cid=cid,
                                platform=SourcePlatform.TELEGRAM,
                                source_url=f"tg://{channel}/{message.id}",
                                author_id=sid,
                                author_name=sname,
                                message_text=text,
                                timestamp=message.date,
                                risk_score=CIDExtractor.calculate_risk_score(text)
                            )
                            self._record_mention(mention)
                            count += 1
                logger.info(f"频道 {channel} 历史完成，{count} 个CID")
            except Exception as e:
                self._stats['errors'] += 1
                logger.error(f"扫描频道 {channel} 失败: {e}")
        self._stats['last_scan_time'] = datetime.utcnow().isoformat()


# ==================== Twitter/X 监控 ====================

class TwitterMonitor(BaseMonitor):
    """
    Twitter/X 监控

    需要: Twitter Developer Bearer Token
    """

    TWITTER_API_BASE = "https://api.twitter.com/2"

    def __init__(
        self,
        bearer_token: str,
        search_queries: List[str] = None,
        poll_interval: int = 60
    ):
        super().__init__()
        self.bearer_token = bearer_token
        self.search_queries = search_queries or [
            'ipfs.io/ipfs/', '#IPFS CID', 'bafybei',
            'cloudflare-ipfs.com', 'dweb.link/ipfs'
        ]
        self.poll_interval = poll_interval
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_tweet_ids: Dict[str, str] = {}

    async def start(self):
        self._is_running = True
        self._session = aiohttp.ClientSession(
            headers={
                'Authorization': f'Bearer {self.bearer_token}',
                'Content-Type': 'application/json'
            }
        )
        logger.info(f"Twitter监控已启动，{len(self.search_queries)} 个查询")

        try:
            while self._is_running:
                await self._poll_tweets()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            if self._session:
                await self._session.close()

    async def stop(self):
        self._is_running = False
        if self._session:
            await self._session.close()

    async def _poll_tweets(self):
        for query in self.search_queries:
            if not self._is_running:
                break
            try:
                params = {
                    'query': query,
                    'max_results': 100,
                    'tweet.fields': 'created_at,author_id,text',
                    'expansions': 'author_id',
                    'user.fields': 'username,name'
                }
                last_id = self._last_tweet_ids.get(query)
                if last_id:
                    params['since_id'] = last_id

                async with self._session.get(
                    f"{self.TWITTER_API_BASE}/tweets/search/recent",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 429:
                        retry_after = int(
                            response.headers.get('retry-after', 60)
                        )
                        logger.warning(f"Twitter限流，等待 {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    if response.status != 200:
                        logger.error(f"Twitter API错误: {response.status}")
                        continue
                    data = await response.json()

                tweets = data.get('data', [])
                users_map = {}
                for user in data.get('includes', {}).get('users', []):
                    users_map[user['id']] = user

                for tweet in tweets:
                    self._stats['messages_scanned'] += 1
                    text = tweet.get('text', '')
                    cids = CIDExtractor.extract_cids(text)
                    if not cids:
                        continue

                    author_id = tweet.get('author_id', 'unknown')
                    author = users_map.get(author_id, {})
                    username = author.get('username', 'unknown')

                    for cid in cids:
                        mention = CIDMention(
                            cid=cid,
                            platform=SourcePlatform.TWITTER,
                            source_url=f"https://twitter.com/{username}/status/{tweet['id']}",
                            author_id=author_id,
                            author_name=username,
                            message_text=text,
                            timestamp=datetime.fromisoformat(
                                tweet['created_at'].replace('Z', '+00:00')
                            ),
                            context={
                                'tweet_id': tweet['id'],
                                'query': query,
                            },
                            risk_score=CIDExtractor.calculate_risk_score(text)
                        )
                        self._record_mention(mention)
                        await self._notify_callbacks(mention)
                        logger.info(
                            f"[Twitter] CID: {cid[:20]}... from @{username}"
                        )

                if tweets:
                    self._last_tweet_ids[query] = tweets[0]['id']

            except aiohttp.ClientError as e:
                self._stats['errors'] += 1
                logger.error(f"Twitter请求失败: {e}")
            except Exception as e:
                self._stats['errors'] += 1
                logger.error(f"Twitter监控错误: {e}", exc_info=True)

            await asyncio.sleep(3)  # 查询间隔
        self._stats['last_scan_time'] = datetime.utcnow().isoformat()


# ==================== Reddit 监控 ====================

class RedditMonitor(BaseMonitor):
    """
    Reddit监控

    使用Reddit JSON API（无需认证）
    """

    REDDIT_BASE = "https://www.reddit.com"

    def __init__(
        self,
        subreddits: List[str] = None,
        poll_interval: int = 120,
        user_agent: str = 'IPFS-Forensics/1.0'
    ):
        super().__init__()
        self.subreddits = subreddits or [
            'ipfs', 'filecoin', 'web3', 'cryptocurrency',
            'darknet', 'privacy', 'hacking', 'netsec'
        ]
        self.poll_interval = poll_interval
        self.user_agent = user_agent
        self._session: Optional[aiohttp.ClientSession] = None
        self._seen_post_ids: Set[str] = set()

    async def start(self):
        self._is_running = True
        self._session = aiohttp.ClientSession(
            headers={'User-Agent': self.user_agent}
        )
        logger.info(f"Reddit监控已启动，{len(self.subreddits)} 个subreddit")

        try:
            while self._is_running:
                await self._scan_subreddits()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            if self._session:
                await self._session.close()

    async def stop(self):
        self._is_running = False
        if self._session:
            await self._session.close()

    async def _scan_subreddits(self):
        for subreddit in self.subreddits:
            if not self._is_running:
                break
            try:
                url = f"{self.REDDIT_BASE}/r/{subreddit}/new.json?limit=50"
                async with self._session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Reddit r/{subreddit}: {response.status}")
                        continue
                    data = await response.json()

                posts = data.get('data', {}).get('children', [])
                for post_data in posts:
                    post = post_data.get('data', {})
                    post_id = post.get('id', '')
                    if post_id in self._seen_post_ids:
                        continue
                    self._seen_post_ids.add(post_id)
                    self._stats['messages_scanned'] += 1

                    text = (
                        f"{post.get('title', '')} "
                        f"{post.get('selftext', '')} "
                        f"{post.get('url', '')}"
                    )
                    cids = CIDExtractor.extract_cids(text)
                    if not cids:
                        continue

                    author = post.get('author', 'unknown')
                    permalink = post.get('permalink', '')

                    for cid in cids:
                        mention = CIDMention(
                            cid=cid,
                            platform=SourcePlatform.REDDIT,
                            source_url=f"{self.REDDIT_BASE}{permalink}",
                            author_id=author,
                            author_name=author,
                            message_text=text[:1000],
                            timestamp=datetime.utcfromtimestamp(
                                post.get('created_utc', time.time())
                            ),
                            context={
                                'subreddit': subreddit,
                                'post_id': post_id,
                                'score': post.get('score', 0),
                                'num_comments': post.get('num_comments', 0),
                                'is_nsfw': post.get('over_18', False)
                            },
                            risk_score=CIDExtractor.calculate_risk_score(text)
                        )

                        if post.get('over_18', False):
                            mention.risk_score = min(
                                mention.risk_score + 0.3, 1.0
                            )

                        self._record_mention(mention)
                        await self._notify_callbacks(mention)
                        logger.info(
                            f"[Reddit] CID: {cid[:20]}... "
                            f"from u/{author} r/{subreddit}"
                        )

                await asyncio.sleep(2)
            except aiohttp.ClientError as e:
                self._stats['errors'] += 1
                logger.error(f"Reddit r/{subreddit} 请求失败: {e}")
            except Exception as e:
                self._stats['errors'] += 1
                logger.error(f"Reddit r/{subreddit} 错误: {e}", exc_info=True)

        self._stats['last_scan_time'] = datetime.utcnow().isoformat()

        if len(self._seen_post_ids) > 50000:
            self._seen_post_ids = set(list(self._seen_post_ids)[-25000:])


# ==================== 暗网论坛监控 ====================

class DarkwebMonitor(BaseMonitor):
    """
    暗网论坛监控

    需要:
    - pip install aiohttp-socks
    - 本地Tor代理 (SOCKS5 127.0.0.1:9050)
    - 仅用于合法执法，需司法授权
    """

    def __init__(
        self,
        tor_proxy: str = 'socks5://127.0.0.1:9050',
        target_sites: List[Dict] = None,
        poll_interval: int = 600
    ):
        super().__init__()
        self.tor_proxy = tor_proxy
        self.target_sites = target_sites or []
        self.poll_interval = poll_interval
        self._session: Optional[aiohttp.ClientSession] = None

    async def start(self):
        self._is_running = True
        try:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(self.tor_proxy)
        except ImportError:
            logger.error("需要安装: pip install aiohttp-socks")
            raise
        except Exception as e:
            logger.error(f"无法连接Tor: {e}")
            raise

        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=60),
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; rv:102.0) '
                    'Gecko/20100101 Firefox/102.0'
                )
            }
        )
        logger.info(f"暗网监控已启动，{len(self.target_sites)} 个站点")

        try:
            while self._is_running:
                await self._scan_sites()
                await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            if self._session:
                await self._session.close()

    async def stop(self):
        self._is_running = False
        if self._session:
            await self._session.close()

    async def _scan_sites(self):
        for site in self.target_sites:
            if not self._is_running:
                break
            site_url = site.get('url', '')
            site_name = site.get('name', 'unknown')
            selectors = site.get('selectors', {})

            try:
                async with self._session.get(site_url) as response:
                    if response.status != 200:
                        logger.warning(f"暗网 {site_name}: {response.status}")
                        continue
                    html = await response.text()

                try:
                    from bs4 import BeautifulSoup
                except ImportError:
                    logger.error("需要安装: pip install beautifulsoup4")
                    return

                soup = BeautifulSoup(html, 'html.parser')
                post_selector = selectors.get('post', 'div.post')
                posts = soup.select(post_selector)

                for post in posts:
                    text = post.get_text(separator=' ', strip=True)
                    self._stats['messages_scanned'] += 1
                    cids = CIDExtractor.extract_cids(text)
                    if not cids:
                        continue

                    author_sel = selectors.get('author', '.username')
                    author_el = post.select_one(author_sel)
                    author = (
                        author_el.get_text(strip=True)
                        if author_el else 'anonymous'
                    )

                    for cid in cids:
                        mention = CIDMention(
                            cid=cid,
                            platform=SourcePlatform.DARKWEB,
                            source_url=site_url,
                            author_id=author,
                            author_name=author,
                            message_text=text[:1000],
                            context={
                                'site_name': site_name,
                                'is_onion': '.onion' in site_url
                            },
                            risk_score=max(
                                CIDExtractor.calculate_risk_score(text), 0.5
                            )
                        )
                        self._record_mention(mention)
                        await self._notify_callbacks(mention)
                        logger.info(
                            f"[Darkweb] CID: {cid[:20]}... from {site_name}"
                        )

            except aiohttp.ClientError as e:
                self._stats['errors'] += 1
                logger.error(f"暗网 {site_name} 访问失败: {e}")
            except Exception as e:
                self._stats['errors'] += 1
                logger.error(f"暗网 {site_name} 错误: {e}", exc_info=True)

        self._stats['last_scan_time'] = datetime.utcnow().isoformat()


# ==================== 统一管理器 ====================

class OSINTManager:
    """
    公开信源监控统一管理器

    管理所有信源监控器的生命周期，统一处理CID发现
    """

    def __init__(self):
        self.monitors: Dict[str, BaseMonitor] = {}
        self.all_mentions: List[CIDMention] = []
        self.cid_index: Dict[str, List[CIDMention]] = defaultdict(list)
        self.author_index: Dict[str, List[CIDMention]] = defaultdict(list)
        self._global_callbacks: List[Callable] = []
        self._is_running = False

    def add_monitor(self, name: str, monitor: BaseMonitor):
        monitor.on_cid_found(self._on_cid_found)
        self.monitors[name] = monitor
        logger.info(f"已添加监控器: {name}")

    def on_cid_found(self, callback: Callable):
        self._global_callbacks.append(callback)

    async def _on_cid_found(self, mention: CIDMention):
        self.all_mentions.append(mention)
        self.cid_index[mention.cid].append(mention)
        self.author_index[mention.author_id].append(mention)

        for cb in self._global_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(mention)
                else:
                    cb(mention)
            except Exception as e:
                logger.error(f"全局回调失败: {e}")

    async def start_all(self):
        self._is_running = True
        tasks = []
        for name, monitor in self.monitors.items():
            logger.info(f"启动监控器: {name}")
            tasks.append(
                asyncio.create_task(self._run_monitor(name, monitor))
            )
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            await self.stop_all()

    async def _run_monitor(self, name: str, monitor: BaseMonitor):
        """带错误恢复的监控器运行"""
        max_retries = 5
        retry_count = 0
        while self._is_running and retry_count < max_retries:
            try:
                await monitor.start()
            except Exception as e:
                retry_count += 1
                wait = min(60 * retry_count, 300)
                logger.error(
                    f"监控器 {name} 崩溃 "
                    f"(第{retry_count}次, 等{wait}s): {e}",
                    exc_info=True
                )
                await asyncio.sleep(wait)
        if retry_count >= max_retries:
            logger.error(f"监控器 {name} 重试耗尽")

    async def stop_all(self):
        self._is_running = False
        for name, monitor in self.monitors.items():
            try:
                await monitor.stop()
                logger.info(f"监控器 {name} 已停止")
            except Exception as e:
                logger.error(f"停止 {name} 出错: {e}")

    def get_all_stats(self) -> dict:
        stats = {}
        for name, monitor in self.monitors.items():
            stats[name] = monitor.get_stats()
        stats['global'] = {
            'total_mentions': len(self.all_mentions),
            'unique_cids': len(self.cid_index),
            'unique_authors': len(self.author_index),
            'high_risk': sum(
                1 for m in self.all_mentions if m.risk_score > 0.7
            )
        }
        return stats

    def get_cid_mentions(self, cid: str) -> List[dict]:
        return [m.to_dict() for m in self.cid_index.get(cid, [])]

    def get_author_activity(self, author_id: str) -> List[dict]:
        return [m.to_dict() for m in self.author_index.get(author_id, [])]

    def get_high_risk_mentions(self, threshold: float = 0.7) -> List[dict]:
        return [
            m.to_dict() for m in self.all_mentions
            if m.risk_score >= threshold
        ]

    def get_cross_platform_cids(self) -> List[dict]:
        """获取跨平台出现的CID"""
        result = []
        for cid, mentions in self.cid_index.items():
            platforms = set(m.platform for m in mentions)
            if len(platforms) > 1:
                result.append({
                    'cid': cid,
                    'platforms': [p.value for p in platforms],
                    'mention_count': len(mentions),
                    'max_risk': max(m.risk_score for m in mentions),
                    'first_seen': min(
                        m.timestamp for m in mentions
                    ).isoformat(),
                    'authors': list(set(m.author_id for m in mentions))
                })
        result.sort(key=lambda x: x['max_risk'], reverse=True)
        return result