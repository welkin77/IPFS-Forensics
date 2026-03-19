"""
IPFS取证系统 - Flask主应用
替代原 api/main_app.py + api/routes/*.py

启动方式: python app.py
访问: http://localhost:5000
"""

import os
import json
import uuid
import logging
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, send_file, session
)

# 数据库
from core.db.database import Base, engine, get_db
from core.db.models import EvidenceRecord, ClueRecord

# 采集层
from core.collector.crawler import IntelligenceCrawler
from core.collector.gateway_monitor import GatewayMonitor

# 证据层
from core.evidence.package import EvidencePackage
from core.evidence.custody import ChainOfCustody
from core.evidence.timestamp import stamp_evidence

# 分析层
from core.analysis.content_analyzer import ContentAnalyzer
from core.analysis.id_profiler import IDProfiler

# 报告层
from core.report.generator import EvidenceReportGenerator
from core.report.pdf_generator import PDFReportGenerator

from utils.logger import setup_logger

# ==================== 初始化 ====================

logger = setup_logger("FlaskApp")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 报告存储目录
REPORTS_DIR = "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

# 单例：采集引擎
crawler = IntelligenceCrawler.get_instance()

# 启动时加载已有CID到去重集合
try:
    db = get_db()
    existing = db.query(ClueRecord.cid).all()
    crawler.load_known_cids([r[0] for r in existing if r[0]])
    db.close()
except Exception:
    pass


# ==================== 模板全局变量 ====================

@app.context_processor
def inject_globals():
    """所有模板都能访问的全局变量"""
    return {
        'operator_name': session.get('operator_name', 'Police_001'),
        'now': datetime.now(),
    }


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """仪表盘首页"""
    db = get_db()
    try:
        evidence_count = db.query(EvidenceRecord).count()
        clue_count = db.query(ClueRecord).count()
        illegal_count = db.query(EvidenceRecord).filter(
            EvidenceRecord.is_illegal == True
        ).count()

        # 最近5条取证记录
        recent_evidence = db.query(EvidenceRecord).order_by(
            EvidenceRecord.created_at.desc()
        ).limit(5).all()

        # 最近5条线索
        recent_clues = db.query(ClueRecord).order_by(
            ClueRecord.discovered_at.desc()
        ).limit(5).all()

        return render_template('index.html',
            evidence_count=evidence_count,
            clue_count=clue_count,
            illegal_count=illegal_count,
            recent_evidence=recent_evidence,
            recent_clues=recent_clues,
            scanner_status=crawler.get_status(),
        )
    finally:
        db.close()


@app.route('/gather')
def gather_page():
    """全网情报采集页面"""
    db = get_db()
    try:
        clues = db.query(ClueRecord).order_by(
            ClueRecord.discovered_at.desc()
        ).limit(50).all()
        return render_template('gather.html',
            clues=clues,
            scanner_status=crawler.get_status(),
        )
    finally:
        db.close()


@app.route('/evidence')
def evidence_page():
    """证据固定提取页面"""
    # 如果是从线索池跳转过来的，带着CID
    target_cid = request.args.get('target_cid', '')
    return render_template('evidence.html', target_cid=target_cid)


@app.route('/dashboard')
def dashboard_page():
    """大盘与历史案件"""
    db = get_db()
    try:
        records = db.query(EvidenceRecord).order_by(
            EvidenceRecord.created_at.desc()
        ).limit(100).all()

        # 统计数据（给ECharts用）
        total = db.query(EvidenceRecord).count()
        illegal = db.query(EvidenceRecord).filter(
            EvidenceRecord.is_illegal == True
        ).count()

        return render_template('dashboard.html',
            records=records,
            total_count=total,
            illegal_count=illegal,
            legal_count=total - illegal,
        )
    finally:
        db.close()


@app.route('/analysis')
def analysis_page():
    """身份画像分析页面"""
    return render_template('analysis.html')


# ==================== API路由（HTMX调用） ====================

@app.route('/api/scan', methods=['POST'])
def api_scan():
    """触发雷达扫描（HTMX调用）"""
    keywords_str = request.form.get('keywords', '')
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

    # 执行扫描
    new_clues = crawler.scan_network(keywords)

    # 入库
    db = get_db()
    try:
        for data in new_clues:
            db_clue = ClueRecord(
                cid=data['cid'],
                source=data['source'],
                keyword=data.get('keyword', '')
            )
            db.add(db_clue)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"线索入库失败: {e}")
    finally:
        db.close()

    # 返回扫描日志片段（HTMX局部刷新）
    return render_template('partials/scan_log.html',
        new_count=len(new_clues),
        clues=new_clues,
        status=crawler.get_status(),
    )


@app.route('/api/clues')
def api_clues():
    """获取线索列表（HTMX局部刷新）"""
    db = get_db()
    try:
        clues = db.query(ClueRecord).order_by(
            ClueRecord.discovered_at.desc()
        ).limit(50).all()
        return render_template('partials/clue_table.html', clues=clues)
    finally:
        db.close()


@app.route('/api/scanner-status')
def api_scanner_status():
    """获取扫描器状态（JSON，前端轮询用）"""
    return jsonify(crawler.get_status())


@app.route('/api/collect', methods=['POST'])
def api_collect():
    """执行取证固定（HTMX调用）"""
    cid = request.form.get('cid', '').strip()
    case_id = request.form.get('case_id', '').strip()
    investigator_id = request.form.get('investigator_id', 'Police_001')

    if not cid:
        return '<div class="alert alert-danger">请输入CID</div>'

    if not case_id:
        case_id = f"CASE-{datetime.now().strftime('%Y-%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    try:
        # 1. 初始化监管链
        custody = ChainOfCustody(case_id=case_id)
        custody.add_record("立案初始化", investigator_id, {"cid": cid})

        # 2. 数据采集
        monitor = GatewayMonitor()
        content = monitor.fetch_cid_content(cid)

        if not content:
            return '<div class="alert alert-danger">无法从IPFS网络获取该CID内容，请检查CID或稍后重试。</div>'

        custody.add_record("数据采集", investigator_id, {
            "bytes_downloaded": len(content)
        })

        # 3. 内容分析
        analyzer = ContentAnalyzer()
        analysis_results = analyzer.analyze(content)

        custody.add_record("内容审查", "System_Analyzer", {
            "file_type": analysis_results['file_type'],
            "is_illegal": analysis_results['is_illegal']
        })

        # 4. 证据固定（多重哈希 + 证据包整体哈希）
        metadata = {
            "investigator": investigator_id,
            "tool": "IPFS_Forensics_V2_Flask",
            "case_number": case_id
        }
        evidence = EvidencePackage(cid=cid, content=content, metadata=metadata)
        integrity_proof = evidence.build_integrity_proof()

        custody.add_record("证据固定", "System_Hasher", {
            "sha256": evidence.hashes['sha256'],
            "integrity_hash": integrity_proof['integrity_hash']
        })

        # 5. 可信时间戳
        timestamp_result = stamp_evidence(evidence.hashes['sha256'])
        custody.add_record("可信时间戳", investigator_id, {
            "tsa_server": timestamp_result.get('tsa_server'),
            "success": timestamp_result.get('success'),
        })

        # 6. 生成报告
        case_info = {
            "case_id": case_id,
            "case_name": "IPFS非法内容取证",
            "generation_time": evidence.timestamp
        }
        report_gen = EvidenceReportGenerator(case_info)
        report_filename = f"report_{case_id}_{uuid.uuid4().hex[:8]}.json"
        report_path = os.path.join(REPORTS_DIR, report_filename)

        report_json_str = report_gen.generate_json_report(
            evidence=evidence,
            custody_chain=custody,
            analysis_results=analysis_results,
            output_path=report_path
        )
        report_data = json.loads(report_json_str)
        report_data['timestamp'] = timestamp_result

        # 7. 数据库持久化
        db = get_db()
        try:
            db_record = EvidenceRecord(
                case_id=case_id,
                investigator_id=investigator_id,
                cid=cid,
                file_type=analysis_results['file_type'],
                file_size=len(content),
                is_illegal=analysis_results['is_illegal'],
                matched_keywords=",".join(
                    analysis_results.get('matched_keywords', [])
                ),
                extracted_text=analysis_results.get('extracted_text', ''),
                sha256=evidence.hashes['sha256'],
                keccak256=evidence.hashes.get('keccak256', ''),
                merkle_root=integrity_proof['integrity_hash'],  # 字段复用：存整体哈希
                report_data=json.dumps(report_data, ensure_ascii=False)
            )
            db.add(db_record)
            db.commit()
            db.refresh(db_record)
            logger.info(f"取证数据已保存，记录ID: {db_record.id}")
        except Exception as e:
            logger.error(f"数据库写入失败: {e}")
            db.rollback()
        finally:
            db.close()

        # 返回结果HTML片段
        return render_template('partials/evidence_result.html',
            success=True,
            case_id=case_id,
            cid=cid,
            report_data=report_data,
            integrity_hash=integrity_proof['integrity_hash'],
            timestamp_result=timestamp_result,
            analysis_results=analysis_results,
            evidence=evidence,
            chain_records=report_data.get('chain_of_custody', []),
        )

    except Exception as e:
        logger.error(f"取证失败: {e}", exc_info=True)
        return f'<div class="alert alert-danger">取证过程发生错误: {str(e)}</div>'

@app.route('/api/export-pdf', methods=['POST'])
def api_export_pdf():
    """导出PDF报告"""
    record_id = request.form.get('record_id')

    db = get_db()
    try:
        record = db.query(EvidenceRecord).filter(
            EvidenceRecord.id == record_id
        ).first()

        if not record or not record.report_data:
            flash('未找到该记录的报告数据', 'danger')
            return redirect(url_for('dashboard_page'))

        report_data = json.loads(record.report_data)
        pdf_gen = PDFReportGenerator()
        filepath = pdf_gen.generate(report_data, record.case_id)

        return send_file(filepath, as_attachment=True)

    except Exception as e:
        flash(f'PDF导出失败: {e}', 'danger')
        return redirect(url_for('dashboard_page'))
    finally:
        db.close()


@app.route('/api/history')
def api_history():
    """历史记录表格（HTMX局部刷新）"""
    db = get_db()
    try:
        records = db.query(EvidenceRecord).order_by(
            EvidenceRecord.created_at.desc()
        ).limit(100).all()
        return render_template('partials/history_table.html', records=records)
    finally:
        db.close()


@app.route('/api/profile', methods=['POST'])
def api_profile():
    """ID画像分析"""
    platform = request.form.get('platform', '')
    user_id = request.form.get('user_id', '')

    profiler = IDProfiler()
    # 注入模拟数据
    profiler.add_id_relation("Telegram", "dark_user99", "IPFS_Node", "Peer_X1Y2", 0.9)
    profiler.add_id_relation("DarkWebForum", "vendor_99", "Telegram", "dark_user99", 0.8)
    profiler.add_id_relation("IPFS_Node", "Peer_X1Y2", "Twitter", "crypto_scam_01", 0.7)

    result = profiler.profile_id(platform, user_id)
    return jsonify(result)


# ==================== 启动 ====================

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("  IPFS取证系统 v2.0 (Flask)")
    logger.info("  访问: http://localhost:5000")
    logger.info("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)