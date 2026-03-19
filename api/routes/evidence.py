import json
import os
import uuid
from fastapi import APIRouter, HTTPException
from api.schemas import CollectRequest, CollectResponse
from core.collector.gateway_monitor import GatewayMonitor
from core.evidence.package import EvidencePackage
from core.evidence.custody import ChainOfCustody
from core.report.generator import EvidenceReportGenerator
from utils.logger import setup_logger
from core.analysis.content_analyzer import ContentAnalyzer
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from core.db.database import get_db, engine, Base
from core.db.models import EvidenceRecord
from typing import List
from api.schemas import EvidenceRecordResponse
from core.evidence.timestamp import stamp_evidence
from fastapi.responses import FileResponse
from core.report.pdf_generator import PDFReportGenerator

# 系统启动时，自动创建数据库表结构（如果表不存在）
Base.metadata.create_all(bind=engine)

logger = setup_logger(__name__)
router = APIRouter(prefix="/evidence", tags=["证据固定 (Evidence)"])

# 确保报告存储目录存在
REPORTS_DIR = "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

@router.post("/collect", response_model=CollectResponse)
async def collect_and_fixate(request: CollectRequest, db: Session = Depends(get_db)):
    """
    接收前端传入的 CID，触发系统进行公网嗅探、下载、多重哈希、构建默克尔树并生成报告。
    """
    logger.info(f"收到 API 取证请求, CID: {request.cid}")
    
    # 1. 初始化监管链
    custody = ChainOfCustody(case_id=request.case_id)
    custody.add_record("立案初始化 (API)", request.investigator_id, {"cid": request.cid})

    # 2. 数据采集
    monitor = GatewayMonitor()
    content = monitor.fetch_cid_content(request.cid)
    
    if not content:
        logger.error(f"无法获取 CID 内容: {request.cid}")
        raise HTTPException(status_code=404, detail="无法从 IPFS 网络获取该 CID 的内容，请稍后再试或检查 CID。")
        
    custody.add_record("数据采集", request.investigator_id, {"bytes_downloaded": len(content)})
    
    # 3.内容解析与审查
    analyzer = ContentAnalyzer()
    analysis_results = analyzer.analyze(content)
    
    custody.add_record("内容审查", "System_Analyzer", {
        "file_type": analysis_results['file_type'],
        "is_illegal": analysis_results['is_illegal']
    })

    # 4. 证据固定
    metadata = {
        "investigator": request.investigator_id,
        "tool": "IPFS_Forensics_API_V1",
        "case_number": request.case_id
    }
    evidence = EvidencePackage(cid=request.cid, content=content, metadata=metadata)
    merkle_proof = evidence.build_merkle_proof()
    
    custody.add_record("证据固定", "System_Hasher", {
        "sha256": evidence.hashes['sha256'],
        "merkle_root": merkle_proof['merkle_root']
    })
    # 5. 申请可信时间戳
    investigator_id = 0
    timestamp_result = stamp_evidence(evidence.hashes['sha256'])
    custody.add_record("可信时间戳", investigator_id, {
    "tsa_server": timestamp_result.get('tsa_server'),
    "success": timestamp_result.get('success'),
    "request_time": timestamp_result.get('request_time')
    })
    # 6. 生成报告
    case_info = {
        "case_id": request.case_id,
        "case_name": "API触发的取证任务",
        "generation_time": evidence.timestamp
    }
    report_gen = EvidenceReportGenerator(case_info)
    report_data['timestamp'] = timestamp_result # 将时间戳信息加入报告数据
    # 使用 UUID 避免文件名冲突
    report_filename = f"report_{request.case_id}_{uuid.uuid4().hex[:8]}.json"
    report_path = os.path.join(REPORTS_DIR, report_filename)
    
    report_json_str = report_gen.generate_json_report(
        evidence=evidence, 
        custody_chain=custody, 
        analysis_results=analysis_results, 
        output_path=report_path
    )
    
    report_data = json.loads(report_json_str)

    # ============数据库持久化逻辑 ============
    try:
        # 将本次取证结果实例化为 ORM 模型
        db_record = EvidenceRecord(
            case_id=request.case_id,
            investigator_id=request.investigator_id,
            cid=request.cid,
            file_type=analysis_results['file_type'],
            file_size=len(content),
            is_illegal=analysis_results['is_illegal'],
            matched_keywords=",".join(analysis_results.get('matched_keywords', [])),
            extracted_text=analysis_results.get('extracted_text', ''),
            sha256=evidence.hashes['sha256'],
            keccak256=evidence.hashes['keccak256'],
            merkle_root=merkle_proof['merkle_root'],
            report_data=json.dumps(report_data, ensure_ascii=False)
        )
        
        # 写入数据库并提交事务
        db.add(db_record)
        db.commit()
        db.refresh(db_record)
        logger.info(f"💾 取证数据已成功永久保存至数据库！记录ID: {db_record.id}")
        
    except Exception as e:
        logger.error(f"数据库写入失败: {str(e)}")
        db.rollback() # 发生错误时回滚事务
    # ==========================================================

    return CollectResponse(
        status="success",
        message="证据固定成功，司法报告已生成并入库",
        case_id=request.case_id,
        merkle_root=merkle_proof['merkle_root'],
        report_data=report_data
    )

@router.get("/history", response_model=List[EvidenceRecordResponse])
def get_evidence_history(db: Session = Depends(get_db)):
    """
    获取历史取证记录列表（按时间倒序，最多返回最新 100 条）
    """
    records = db.query(EvidenceRecord).order_by(EvidenceRecord.created_at.desc()).limit(100).all()
    return records

pdf_gen = PDFReportGenerator()

@router.post("/export-pdf")
async def export_pdf(request: dict):
    """导出PDF取证报告"""
    report_data = request.get('report_data', {})
    case_id = request.get('case_id', '')
    
    try:
        filepath = pdf_gen.generate(report_data, case_id)
        return FileResponse(
            filepath,
            media_type='application/pdf',
            filename=os.path.basename(filepath)
        )
    except Exception as e:
        return {"error": True, "message": str(e)}