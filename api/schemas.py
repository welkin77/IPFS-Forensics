from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class CollectRequest(BaseModel):
    """前端发起取证请求的模型"""
    cid: str = Field(..., title="IPFS CID", description="需要抓取和固定的目标CID")
    investigator_id: str = Field("System_API", title="取证人员ID")
    case_id: str = Field("CASE-AUTO-001", title="案件编号")

class CollectResponse(BaseModel):
    """取证结果响应模型"""
    status: str
    message: str
    case_id: str
    merkle_root: Optional[str] = None
    report_data: Optional[Dict[str, Any]] = None

class ProfileRequest(BaseModel):
    """前端发起画像分析请求的模型"""
    platform: str = Field(..., example="Telegram")
    user_id: str = Field(..., example="dark_user99")

class ProfileResponse(BaseModel):
    """画像分析响应模型"""
    seed_node: str
    related_nodes: List[str]
    node_count: int
    edge_count: int

class EvidenceRecordResponse(BaseModel):
    """历史取证记录响应模型"""
    id: int
    case_id: str
    investigator_id: str
    cid: str
    file_type: str
    file_size: int
    is_illegal: bool
    matched_keywords: str
    created_at: datetime
    report_data: str

    class Config:
        from_attributes = True  # 允许 Pydantic 自动从 SQLAlchemy ORM 模型中读取数据