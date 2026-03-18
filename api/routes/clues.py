from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime

from core.db.database import get_db
from core.db.models import ClueRecord
from core.collector.crawler import IntelligenceCrawler

router = APIRouter(prefix="/clues", tags=["情报采集 (Clues)"])

# Pydantic 响应模型
class ClueResponse(BaseModel):
    id: int
    cid: str
    source: str
    keyword: str
    status: str
    discovered_at: datetime
    class Config:
        from_attributes = True

class ScanRequest(BaseModel):
    keywords: List[str]

@router.post("/scan", response_model=List[ClueResponse])
def trigger_scan(request: ScanRequest, db: Session = Depends(get_db)):
    """触发多源爬虫扫描并将结果入库"""
    crawler = IntelligenceCrawler()
    new_clues_data = crawler.scan_network(request.keywords)
    
    saved_clues = []
    for data in new_clues_data:
        db_clue = ClueRecord(
            cid=data['cid'],
            source=data['source'],
            keyword=data['keyword']
        )
        db.add(db_clue)
        db.commit()
        db.refresh(db_clue)
        saved_clues.append(db_clue)
        
    return saved_clues

@router.get("/list", response_model=List[ClueResponse])
def get_clues(db: Session = Depends(get_db)):
    """获取线索池列表"""
    return db.query(ClueRecord).order_by(ClueRecord.discovered_at.desc()).limit(50).all()