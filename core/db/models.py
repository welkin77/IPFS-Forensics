from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from core.db.database import Base

class EvidenceRecord(Base):
    """持久化存储的证据记录表"""
    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String, index=True, comment="案件编号")
    investigator_id = Column(String, comment="取证警员ID")
    
    cid = Column(String, index=True, comment="IPFS CID")
    file_type = Column(String, comment="文件类型")
    file_size = Column(Integer, comment="文件大小(Bytes)")
    
    is_illegal = Column(Boolean, default=False, comment="是否违法")
    matched_keywords = Column(String, default="", comment="命中的敏感词")
    extracted_text = Column(String, default="", comment="提取的文本摘要")
    
    sha256 = Column(String, comment="SHA-256")
    keccak256 = Column(String, comment="Keccak-256")
    merkle_root = Column(String, comment="证据默克尔树根")
    
    created_at = Column(DateTime(timezone=True), default=datetime.now) 

    report_data = Column(String, default="", comment="完整取证报告JSON数据")

class ClueRecord(Base):
    """全网嗅探获取的情报线索池"""
    __tablename__ = "clue_records"

    id = Column(Integer, primary_key=True, index=True)
    cid = Column(String, index=True, comment="发现的可疑CID")
    source = Column(String, comment="来源渠道 (如: DHT, Telegram, 暗网)")
    keyword = Column(String, comment="关联的监控关键字")
    status = Column(String, default="pending", comment="状态: pending(待取证), processed(已固定)")
    discovered_at = Column(DateTime(timezone=True), default=datetime.now)