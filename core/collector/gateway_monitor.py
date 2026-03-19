"""
改进后的网关监控模块
核心改动：
1. 并发请求多个网关（asyncio.gather）
2. 引入熔断器，跳过不可用的网关
3. 先HEAD请求检查大小，再GET下载
"""

import asyncio
import logging
import time
from typing import Optional, Tuple

import aiohttp

from utils.error_handler import CircuitBreaker, GatewayError

logger = logging.getLogger(__name__)


class GatewayMonitor:
    """改进后的IPFS网关监控"""

    DEFAULT_GATEWAYS = [
        {'name': 'local', 'url': 'http://127.0.0.1:8080/ipfs/', 'needs_proxy': False},
        {'name': 'ipfs.io', 'url': 'https://ipfs.io/ipfs/', 'needs_proxy': True},
        {'name': 'cloudflare', 'url': 'https://cloudflare-ipfs.com/ipfs/', 'needs_proxy': True},
        {'name': 'dweb', 'url': 'https://dweb.link/ipfs/', 'needs_proxy': True},
        {'name': 'pinata', 'url': 'https://gateway.pinata.cloud/ipfs/', 'needs_proxy': True},
    ]

    def __init__(
        self,
        gateways: list = None,
        max_file_size: int = 50 * 1024 * 1024,  # 50MB
        timeout: int = 30,
        proxy: str = None  # 'http://127.0.0.1:7890'
    ):
        self.gateways = gateways or self.DEFAULT_GATEWAYS
        self.max_file_size = max_file_size
        self.timeout = timeout
        self.proxy = proxy

        # 每个网关一个熔断器
        self._breakers = {
            gw['name']: CircuitBreaker(
                name=gw['name'],
                failure_threshold=3,
                recovery_timeout=120
            )
            for gw in self.gateways
        }

        # 统计
        self._stats = {gw['name']: {'success': 0, 'fail': 0, 'avg_ms': 0} for gw in self.gateways}

    async def fetch_cid_content(self, cid: str) -> Optional[bytes]:
        """
        并发从多个网关获取CID内容，返回最快成功的结果
        """
        # 过滤出未熔断的网关
        available = [
            gw for gw in self.gateways
            if self._breakers[gw['name']].can_proceed()
        ]

        if not available:
            logger.error("所有网关均已熔断，无法获取内容")
            raise GatewayError("所有网关不可用", gateway="all")

        # 并发请求
        tasks = [
            self._fetch_from_gateway(gw, cid)
            for gw in available
        ]

        # 用 asyncio.gather 并发，返回第一个成功的
        done, pending = await asyncio.wait(
            [asyncio.create_task(t) for t in tasks],
            return_when=asyncio.FIRST_COMPLETED
        )

        # 取消剩余任务
        for task in pending:
            task.cancel()

        # 检查结果
        for task in done:
            try:
                result = task.result()
                if result is not None:
                    return result
            except Exception:
                continue

        # 如果第一批没成功，等待其余
        if pending:
            done2, _ = await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)
            for task in done2:
                try:
                    result = task.result()
                    if result is not None:
                        return result
                except Exception:
                    continue

        logger.warning(f"所有网关均无法获取CID: {cid}")
        return None

    async def _fetch_from_gateway(
        self, gw: dict, cid: str
    ) -> Optional[bytes]:
        """从单个网关获取内容"""
        name = gw['name']
        url = f"{gw['url']}{cid}"
        proxy = self.proxy if gw.get('needs_proxy') else None
        breaker = self._breakers[name]

        start = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                # 1. HEAD请求检查大小
                async with session.head(
                    url,
                    timeout=aiohttp.ClientTimeout(total=10),
                    proxy=proxy,
                    ssl=False
                ) as head_resp:
                    if head_resp.status != 200:
                        raise GatewayError(
                            f"HEAD {head_resp.status}",
                            gateway=name
                        )
                    
                    content_length = int(
                        head_resp.headers.get('Content-Length', 0)
                    )
                    if content_length > self.max_file_size:
                        logger.warning(
                            f"[{name}] 文件过大: "
                            f"{content_length / 1024 / 1024:.1f}MB > "
                            f"{self.max_file_size / 1024 / 1024:.0f}MB"
                        )
                        return None

                # 2. GET下载内容
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    proxy=proxy,
                    ssl=False
                ) as resp:
                    if resp.status != 200:
                        raise GatewayError(
                            f"GET {resp.status}",
                            gateway=name
                        )
                    
                    content = await resp.read()

            elapsed = (time.time() - start) * 1000
            breaker.record_success()

            # 更新统计
            s = self._stats[name]
            s['success'] += 1
            s['avg_ms'] = (s['avg_ms'] * (s['success'] - 1) + elapsed) / s['success']

            logger.info(
                f"[{name}] 成功获取 {cid[:16]}... "
                f"大小={len(content)} 耗时={elapsed:.0f}ms"
            )
            return content

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            breaker.record_failure(e)
            self._stats[name]['fail'] += 1
            logger.debug(f"[{name}] 获取失败: {e}")
            return None

    def get_gateway_status(self) -> list:
        """获取所有网关状态"""
        return [
            {
                'name': gw['name'],
                'url': gw['url'],
                'breaker': self._breakers[gw['name']].get_status(),
                'stats': self._stats[gw['name']]
            }
            for gw in self.gateways
        ]