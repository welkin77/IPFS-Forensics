"""
IPFS公开网关监控模块
位置: core/collector/gateway_monitor.py
对应设计方案 3.1.2

职责：通过多个IPFS公共网关下载CID对应的文件内容
使用场景：取证固定阶段，需要拿到文件二进制内容来计算哈希

设计要点：
1. 同步请求（配合Flask）
2. 多网关容错：一个失败自动尝试下一个
3. 失败计数：连续失败的网关自动跳过一段时间
4. 文件大小预检：先HEAD检查，避免下载巨型文件
5. 代理支持：公网网关可通过代理访问
"""

import time
import logging
from typing import Optional, List, Dict

import requests
import urllib3

# 禁用SSL警告（部分网关证书问题）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class GatewayMonitor:
    """IPFS网关内容下载器"""

    DEFAULT_GATEWAYS = [
        {'name': 'local',      'url': 'http://127.0.0.1:8080/ipfs/', 'needs_proxy': False},
        {'name': 'ipfs.io',    'url': 'https://ipfs.io/ipfs/',       'needs_proxy': True},
        {'name': 'cloudflare', 'url': 'https://cloudflare-ipfs.com/ipfs/', 'needs_proxy': True},
        {'name': 'dweb.link',  'url': 'https://dweb.link/ipfs/',     'needs_proxy': True},
        {'name': 'pinata',     'url': 'https://gateway.pinata.cloud/ipfs/', 'needs_proxy': True},
        {'name': 'w3s.link',   'url': 'https://w3s.link/ipfs/',      'needs_proxy': True},
    ]

    # 网关连续失败N次后，跳过一段时间
    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 120

    def __init__(
        self,
        gateways: List[Dict] = None,
        max_file_size: int = 50 * 1024 * 1024,  # 50MB
        timeout: int = 30,
        proxy: str = None,  # 例: 'http://127.0.0.1:7890'
    ):
        self.gateways = gateways or self.DEFAULT_GATEWAYS
        self.max_file_size = max_file_size
        self.timeout = timeout
        self.proxy = proxy

        # 每个网关的失败计数和冷却时间
        self._failures: Dict[str, int] = {gw['name']: 0 for gw in self.gateways}
        self._cooldown_until: Dict[str, float] = {gw['name']: 0 for gw in self.gateways}

        # 统计信息
        self._stats: Dict[str, Dict] = {
            gw['name']: {'success': 0, 'fail': 0, 'total_ms': 0}
            for gw in self.gateways
        }

    def fetch_cid_content(self, cid: str) -> Optional[bytes]:
        """
        从多个网关依次尝试下载CID内容

        Args:
            cid: IPFS CID (如 QmXxx... 或 bafyxxx...)

        Returns:
            文件内容的bytes，全部失败返回None
        """
        if not cid or not cid.strip():
            logger.error("CID为空")
            return None

        cid = cid.strip()
        now = time.time()

        for gw in self.gateways:
            name = gw['name']

            # 检查冷却期
            if now < self._cooldown_until[name]:
                remaining = int(self._cooldown_until[name] - now)
                logger.debug(f"[{name}] 冷却中，跳过（剩余{remaining}s）")
                continue

            # 尝试下载
            content = self._try_gateway(gw, cid)
            if content is not None:
                return content

        logger.warning(f"所有网关均无法获取CID: {cid}")
        return None

    def _try_gateway(self, gw: Dict, cid: str) -> Optional[bytes]:
        """从单个网关下载内容"""
        name = gw['name']
        url = f"{gw['url']}{cid}"
        start = time.time()

        # 构建代理配置
        proxies = None
        if gw.get('needs_proxy') and self.proxy:
            proxies = {'http': self.proxy, 'https': self.proxy}

        try:
            # 第1步：HEAD请求预检文件大小
            head_resp = requests.head(
                url, timeout=10, proxies=proxies,
                verify=False, allow_redirects=True
            )

            if head_resp.status_code != 200:
                # HEAD不一定所有网关都支持，跳过预检直接GET
                if head_resp.status_code >= 500:
                    raise Exception(f"HEAD返回{head_resp.status_code}")
            else:
                content_length = int(head_resp.headers.get('Content-Length', 0))
                if content_length > self.max_file_size:
                    logger.warning(
                        f"[{name}] 文件过大: {content_length / 1024 / 1024:.1f}MB，跳过"
                    )
                    return None

            # 第2步：GET下载内容
            resp = requests.get(
                url, timeout=self.timeout, proxies=proxies,
                verify=False, allow_redirects=True
            )

            if resp.status_code != 200:
                raise Exception(f"GET返回{resp.status_code}")

            content = resp.content

            # 二次校验大小（有些网关HEAD不返回Content-Length）
            if len(content) > self.max_file_size:
                logger.warning(f"[{name}] 下载后发现文件过大: {len(content)}bytes")
                return None

            # 成功
            elapsed_ms = (time.time() - start) * 1000
            self._record_success(name, elapsed_ms)

            logger.info(
                f"[{name}] 成功获取 {cid[:20]}... "
                f"大小={len(content)}bytes 耗时={elapsed_ms:.0f}ms"
            )
            return content

        except requests.exceptions.Timeout:
            self._record_failure(name)
            logger.debug(f"[{name}] 超时")
            return None

        except requests.exceptions.ConnectionError:
            self._record_failure(name)
            logger.debug(f"[{name}] 连接失败")
            return None

        except Exception as e:
            self._record_failure(name)
            logger.debug(f"[{name}] 失败: {e}")
            return None

    def _record_success(self, name: str, elapsed_ms: float):
        """记录成功"""
        self._failures[name] = 0
        s = self._stats[name]
        s['success'] += 1
        s['total_ms'] += elapsed_ms

    def _record_failure(self, name: str):
        """记录失败，达到阈值进入冷却"""
        self._failures[name] += 1
        self._stats[name]['fail'] += 1

        if self._failures[name] >= self.FAILURE_THRESHOLD:
            self._cooldown_until[name] = time.time() + self.COOLDOWN_SECONDS
            logger.warning(
                f"[{name}] 连续失败{self._failures[name]}次，"
                f"冷却{self.COOLDOWN_SECONDS}s"
            )

    def get_status(self) -> List[Dict]:
        """获取所有网关状态（给前端展示用）"""
        now = time.time()
        result = []
        for gw in self.gateways:
            name = gw['name']
            s = self._stats[name]
            avg_ms = s['total_ms'] / s['success'] if s['success'] > 0 else 0
            result.append({
                'name': name,
                'url': gw['url'],
                'success_count': s['success'],
                'fail_count': s['fail'],
                'avg_ms': round(avg_ms, 1),
                'is_cooling': now < self._cooldown_until[name],
                'failures': self._failures[name],
            })
        return result