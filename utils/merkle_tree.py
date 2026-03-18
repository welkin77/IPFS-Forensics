import hashlib
from typing import List, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

class MerkleTree:
    """
    自主实现的轻量级默克尔树 (Merkle Tree)
    完全移除对第三方陈旧库(merkletools/pysha3)的依赖
    基于标准 hashlib.sha256 实现
    """
    def __init__(self):
        self.leaves: List[bytes] = []
        self.levels: List[List[bytes]] = []
        self.is_ready: bool = False

    def add_leaf(self, data: bytes, do_hash: bool = False) -> None:
        """
        添加叶子节点
        Args:
            data: 节点数据 (bytes)
            do_hash: 是否在插入前先对数据进行一次 SHA256 哈希
        """
        self.is_ready = False
        if do_hash:
            leaf = hashlib.sha256(data).digest()
        else:
            leaf = data
        self.leaves.append(leaf)

    def make_tree(self) -> None:
        """构建默克尔树"""
        self.is_ready = False
        if not self.leaves:
            logger.warning("没有叶子节点，无法构建默克尔树")
            return

        self.levels = [self.leaves]
        
        # 自底向上逐层计算，直到只剩一个根节点
        while len(self.levels[-1]) > 1:
            current_level = self.levels[-1]
            next_level = []
            
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                # 如果是奇数个节点，则复制最后一个节点与自己配对（标准默克尔树处理方式）
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                
                # Hash(left + right)
                combined = left + right
                parent_hash = hashlib.sha256(combined).digest()
                next_level.append(parent_hash)
                
            self.levels.append(next_level)
            
        self.is_ready = True
        logger.debug("默克尔树构建完成")

    def get_merkle_root(self) -> Optional[str]:
        """获取 Hex 格式的默克尔根"""
        if not self.is_ready or not self.levels:
            return None
        return self.levels[-1][0].hex()

    def get_leaf_count(self) -> int:
        """获取叶子节点数量"""
        return len(self.leaves)