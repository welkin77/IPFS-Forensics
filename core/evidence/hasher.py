import hashlib
from typing import Dict
from eth_hash.auto import keccak
from utils.logger import setup_logger

logger = setup_logger(__name__)

class EvidenceHasher:
    """多重哈希计算模块（保证司法完整性与区块链兼容性）"""

    def __init__(self):
        # 采用纯净方案：SHA256(通用司法标准) + SHA512(高强度防碰撞) + Keccak256(以太坊锚定)
        self.algorithms = ['sha256', 'sha512', 'keccak256']

    def compute_hashes(self, content: bytes) -> Dict[str, str]:
        results: Dict[str, str] = {}
        try:
            results['sha256'] = hashlib.sha256(content).hexdigest()
            results['sha512'] = hashlib.sha512(content).hexdigest() # 替换原有的 blake3
            results['keccak256'] = keccak(content).hex()
            
            logger.info("多重哈希计算完成 (SHA256, SHA512, Keccak-256)")
        except Exception as e:
            logger.error(f"哈希计算过程发生异常: {str(e)}")
            raise
        return results