"""
证据包封装模块
位置: core/evidence/package.py
对应设计方案 3.2.1 + 3.2.2

职责：
1. 对文件内容计算多重哈希（3.2.1）
2. 构建证据包JSON并计算整体完整性哈希（3.2.2）

不再使用 Merkle 树，改为证据包整体 SHA-256 哈希
"""

import json
import hashlib
import datetime
from typing import Dict, Any

from core.evidence.hasher import EvidenceHasher
from utils.logger import setup_logger

logger = setup_logger(__name__)


class EvidencePackage:
    """司法证据包封装"""

    def __init__(self, cid: str, content: bytes, metadata: Dict[str, Any]):
        self.cid: str = cid
        self.content: bytes = content
        self.metadata: Dict[str, Any] = metadata
        self.timestamp: str = datetime.datetime.utcnow().isoformat()

        # 计算多重哈希（SHA-256, SHA-512, Keccak-256）
        hasher = EvidenceHasher()
        self.hashes: Dict[str, str] = hasher.compute_hashes(self.content)

        # 证据包整体哈希（替代 Merkle Root）
        self.integrity_hash: str = ""

    def build_integrity_proof(self) -> Dict[str, Any]:
        """
        构建证据包完整性证明

        将 CID、内容哈希、时间戳、元数据组合为 JSON 对象，
        按 key 排序序列化后计算 SHA-256 整体哈希。

        对应设计方案 3.2.2:
        > "将证据相关数据构建为JSON对象，并对整个对象计算完整性哈希"

        Returns:
            {
                'integrity_hash': '整体SHA-256哈希',
                'package_fields': 包含的字段数量,
                'proof_level': 'full'
            }
        """
        # 构建证据包结构体
        package = {
            'cid': self.cid,
            'content_hash': self.hashes,
            'acquisition_time': self.timestamp,
            'operator': self.metadata.get('investigator', ''),
            'tool': self.metadata.get('tool', ''),
            'case_number': self.metadata.get('case_number', ''),
        }

        # 按 key 排序后序列化，保证一致性
        package_str = json.dumps(package, sort_keys=True, ensure_ascii=False)
        self.integrity_hash = hashlib.sha256(
            package_str.encode('utf-8')
        ).hexdigest()

        logger.info(f"证据包完整性哈希: {self.integrity_hash}")

        return {
            'integrity_hash': self.integrity_hash,
            'package_fields': len(package),
            'proof_level': 'full'
        }