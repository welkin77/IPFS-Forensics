import re
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime


class CollectRequest(BaseModel):
    """前端发起取证请求的模型"""
    cid: str = Field(..., title="IPFS CID", description="需要抓取和固定的目标CID")
    investigator_id: str = Field("System_API", title="取证人员ID")
    case_id: str = Field("CASE-AUTO-001", title="案件编号")

    @validator('cid')
    def validate_cid(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('CID 不能为空')
        # CIDv0: Qm开头，46字符
        if re.match(r'^Qm[1-9A-HJ-NP-Za-km-z]{44}$', v):
            return v
        # CIDv1: bafy开头
        if re.match(r'^bafy[a-z2-7]{55,}$', v):
            return v
        # CIDv1: bafk开头 (raw codec)
        if re.match(r'^bafk[a-z2-7]{55,}$', v):
            return v
        raise ValueError(
            f'无效的 CID 格式: "{v}"。'
            f'CIDv0 应为 Qm 开头共 46 字符，CIDv1 应为 bafy/bafk 开头。'
        )

    @validator('investigator_id')
    def validate_investigator_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('取证人员 ID 不能为空')
        if len(v) > 100:
            raise ValueError('取证人员 ID 过长（最多100字符）')
        return v

    @validator('case_id')
    def validate_case_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('案件编号不能为空')
        if len(v) > 100:
            raise ValueError('案件编号过长（最多100字符）')
        # 允许 CASE- 开头或自定义格式，只做基本安全检查
        if re.search(r'[<>"\';]', v):
            raise ValueError('案件编号包含非法字符')
        return v


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

    @validator('platform')
    def validate_platform(cls, v):
        v = v.strip()
        allowed = ['Telegram', 'Twitter', 'Reddit', 'DarkWebForum', 'IPFS_Node', 'Unknown']
        if v not in allowed:
            raise ValueError(f'不支持的平台: "{v}"，允许的值: {", ".join(allowed)}')
        return v

    @validator('user_id')
    def validate_user_id(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('用户 ID 不能为空')
        if len(v) > 200:
            raise ValueError('用户 ID 过长（最多200字符）')
        if re.search(r'[<>"\';]', v):
            raise ValueError('用户 ID 包含非法字符')
        return v


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
        from_attributes = True


class ClueResponse(BaseModel):
    """线索记录响应模型"""
    id: Optional[int] = None
    cid: str
    source: str
    discovered_at: Optional[datetime] = None
    status: Optional[str] = 'new'

    class Config:
        from_attributes = True


class ScanRequest(BaseModel):
    """雷达扫描请求模型"""
    keywords: List[str] = Field(default_factory=list, description="扫描关键词列表")

    @validator('keywords', each_item=True)
    def validate_keyword(cls, v):
        v = v.strip()
        if len(v) > 50:
            raise ValueError(f'单个关键词过长（最多50字符）: "{v[:20]}..."')
        if re.search(r'[<>"\';]', v):
            raise ValueError(f'关键词包含非法字符: "{v}"')
        return v


class ErrorResponse(BaseModel):
    """统一错误响应模型"""
    error: bool = True
    code: str = 'UNKNOWN_ERROR'
    message: str
    detail: Optional[str] = None
    timestamp: Optional[str] = None