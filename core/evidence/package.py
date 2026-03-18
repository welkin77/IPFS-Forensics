import datetime
from typing import Dict, Any, Optional
# 移除：from merkletools import MerkleTools
from utils.merkle_tree import MerkleTree  # 引入自主实现的类
from core.evidence.hasher import EvidenceHasher
from utils.logger import setup_logger

logger = setup_logger(__name__)

class EvidencePackage:
    """司法证据包封装与默克尔树构建"""

    def __init__(self, cid: str, content: bytes, metadata: Dict[str, Any]):
        self.cid: str = cid
        self.content: bytes = content
        self.metadata: Dict[str, Any] = metadata
        self.timestamp: str = datetime.datetime.utcnow().isoformat()
        
        hasher = EvidenceHasher()
        self.hashes = hasher.compute_hashes(self.content)
        
        self.merkle_tree: Optional[MerkleTree] = None
        self.merkle_root: Optional[str] = None

    def build_merkle_proof(self) -> Dict[str, Any]:
        """构建证据的默克尔树证明"""
        mt = MerkleTree()
        
        # 添加核心证据元素到默克尔树 (传入 bytes, 并要求 do_hash=True 进行哈希)
        mt.add_leaf(self.cid.encode(), do_hash=True)
        mt.add_leaf(self.hashes['sha256'].encode(), do_hash=True)
        mt.add_leaf(self.timestamp.encode(), do_hash=True)
        
        # 添加元数据
        for key, value in self.metadata.items():
            leaf_data = f"{key}:{value}".encode()
            mt.add_leaf(leaf_data, do_hash=True)
            
        mt.make_tree()
        self.merkle_tree = mt
        self.merkle_root = mt.get_merkle_root()
        
        logger.info(f"默克尔树构建完成，Root Hash: {self.merkle_root}")
        
        return {
            'merkle_root': self.merkle_root,
            'leaf_count': mt.get_leaf_count(),
            'is_ready': mt.is_ready,
            'proof_level': 'full'
        }