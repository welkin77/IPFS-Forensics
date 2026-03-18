import datetime
import hashlib
import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class CustodyRecord:
    """单条监管链记录"""
    timestamp: str
    action: str
    operator: str
    details: str
    previous_hash: str
    record_hash: str = ""

    def calculate_hash(self) -> str:
        """计算当前记录的哈希值"""
        data = f"{self.timestamp}{self.action}{self.operator}{self.details}{self.previous_hash}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

class ChainOfCustody:
    """证据监管链 (Chain of Custody) 记录系统"""

    def __init__(self, case_id: str):
        self.case_id: str = case_id
        self.records: List[CustodyRecord] = []
        self._last_hash: str = "GENESIS_BLOCK"  # 创世哈希

    def add_record(self, action: str, operator: str, details: Dict[str, Any]) -> str:
        """
        添加一条监管记录
        
        Args:
            action (str): 操作类型 (如: '采集', '固定', '分析')
            operator (str): 操作人/系统组件标识
            details (Dict): 操作详细信息
            
        Returns:
            str: 当前记录的哈希值
        """
        timestamp = datetime.datetime.utcnow().isoformat()
        details_str = json.dumps(details, sort_keys=True)
        
        record = CustodyRecord(
            timestamp=timestamp,
            action=action,
            operator=operator,
            details=details_str,
            previous_hash=self._last_hash
        )
        record.record_hash = record.calculate_hash()
        
        self.records.append(record)
        self._last_hash = record.record_hash
        
        logger.info(f"监管链增加记录: [{action}] by {operator} (Hash: {record.record_hash[:8]}...)")
        return record.record_hash

    def export_chain(self) -> List[Dict[str, Any]]:
        """导出完整的监管链记录"""
        return [asdict(record) for record in self.records]