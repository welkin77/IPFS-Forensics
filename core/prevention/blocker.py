"""
内容阻断与预防模块
对应IF-DSS框架 4.4 Prevention阶段

三种预防策略：
1. 向IPFS官方网关发送abuse report
2. 通过本地IPFS节点unpin内容
3. 向pinning服务发送移除请求
"""

import logging
import requests

logger = logging.getLogger(__name__)


class ContentBlocker:
    """IPFS内容阻断器"""

    # 各网关的abuse report接口
    ABUSE_ENDPOINTS = {
        'ipfs.io': 'https://ipfs.tech/help/',
        'cloudflare': 'https://www.cloudflare.com/abuse/form',
        'pinata': 'https://www.pinata.cloud/contact',
    }

    IPFS_API = "http://127.0.0.1:5001/api/v0"

    def unpin_from_local_node(self, cid: str) -> dict:
        """
        从本地IPFS节点unpin内容（IF-DSS 4.4.2）
        取消固定后，内容将在下次GC时被清理
        """
        try:
            # Unpin
            resp = requests.post(
                f"{self.IPFS_API}/pin/rm",
                params={'arg': cid},
                timeout=10
            )
            if resp.status_code == 200:
                logger.info(f"[阻断] 已unpin CID: {cid}")
                return {'success': True, 'action': 'unpin', 'cid': cid}
            else:
                return {'success': False, 'error': f'状态码 {resp.status_code}'}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def trigger_gc(self) -> dict:
        """触发本地IPFS节点垃圾回收"""
        try:
            resp = requests.post(
                f"{self.IPFS_API}/repo/gc",
                timeout=30
            )
            return {'success': resp.status_code == 200}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def generate_abuse_report(self, cid: str, reason: str, urls: list = None) -> dict:
        """
        生成abuse report内容（IF-DSS 4.4.1）
        目前无法自动提交（各网关需人工填表），
        但可以生成报告文本供取证人员复制提交
        """
        gateway_urls = urls or [
            f"https://ipfs.io/ipfs/{cid}",
            f"https://cloudflare-ipfs.com/ipfs/{cid}",
            f"https://dweb.link/ipfs/{cid}",
        ]

        report_text = f"""=== IPFS内容阻断举报 ===
CID: {cid}
举报原因: {reason}
涉及网关URL:
{chr(10).join('  - ' + u for u in gateway_urls)}

举报提交地址:
  - IPFS官方: https://ipfs.tech/help/
  - Cloudflare: https://www.cloudflare.com/abuse/form
  - Pinata: https://www.pinata.cloud/contact

请将以上信息提交至对应网关的举报页面。
"""
        return {
            'cid': cid,
            'report_text': report_text,
            'submit_urls': self.ABUSE_ENDPOINTS
        }

    def get_prevention_status(self, cid: str) -> dict:
        """检查CID在本地节点的固定状态"""
        try:
            resp = requests.post(
                f"{self.IPFS_API}/pin/ls",
                params={'arg': cid},
                timeout=5
            )
            is_pinned = resp.status_code == 200
            return {'cid': cid, 'is_pinned': is_pinned}
        except Exception:
            return {'cid': cid, 'is_pinned': False, 'node_offline': True}