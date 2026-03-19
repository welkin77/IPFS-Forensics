"""
IPFS取证系统 - Flask主应用
基于IF-DSS框架（Son et al., 2023, DFRWS APAC）

启动: python app.py
访问: http://localhost:5000
"""

import os
import json
import uuid
import logging
import requests
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, send_file, session
)

# 数据库
from core.db.database import Base, engine, get_db
from core.db.models import EvidenceRecord, ClueRecord

# 数据采集层（IF-DSS: Collection）
from core.collector.crawler import IntelligenceCrawler
from core.collector.gateway_monitor import GatewayMonitor
from core.collector.forum_scanner import ForumScanner
from core.collector.dht_sniffer import DHTSniffer

# 证据固定层（IF-DSS: Preservation）
from core.evidence.package import EvidencePackage
from core.evidence.custody import ChainOfCustody
from core.evidence.timestamp import stamp_evidence

# 情报分析层（IF-DSS: Examination & Analysis）
from core.analysis.content_analyzer import ContentAnalyzer
from core.analysis.id_profiler import IDProfiler

# 报告生成
from core.report.generator import EvidenceReportGenerator
from core.report.pdf_generator import PDFReportGenerator

from utils.logger import setup_logger

# ==================== 初始化 ====================

logger = setup_logger("FlaskApp")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 报告目录
REPORTS_DIR = "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

# 单例：采集引擎
crawler = IntelligenceCrawler.get_instance()

# 单例：CID提取器
_forum_scanner = ForumScanner()

# 单例：DHT嗅探器
_dht_sniffer = DHTSniffer()

# 启动时加载已有CID到去重集合
try:
    _db = get_db()
    _existing = _db.query(ClueRecord.cid).all()
    crawler.load_known_cids([r[0] for r in _existing if r[0]])
    _db.close()
except Exception:
    pass


# ==================== 模板全局变量 ====================

@app.context_processor
def inject_globals():
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

        recent_evidence = db.query(EvidenceRecord).order_by(
            EvidenceRecord.created_at.desc()
        ).limit(5).all()

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
    """全网情报采集"""
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
    """证据固定提取"""
    target_cid = request.args.get('target_cid', '')
    return render_template('evidence.html', target_cid=target_cid)


@app.route('/dashboard')
def dashboard_page():
    """历史案件大盘"""
    db = get_db()
    try:
        records = db.query(EvidenceRecord).order_by(
            EvidenceRecord.created_at.desc()
        ).limit(100).all()

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
    """身份画像分析"""
    return render_template('analysis.html')


# ==================== 数据采集API（IF-DSS: Collection） ====================

@app.route('/api/scan', methods=['POST'])
def api_scan():
    """触发雷达扫描"""
    keywords_str = request.form.get('keywords', '')
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]

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

    return render_template('partials/scan_log.html',
        new_count=len(new_clues),
        clues=new_clues,
        status=crawler.get_status(),
    )


@app.route('/api/clues')
def api_clues():
    """获取线索列表"""
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
    """扫描器状态（JSON）"""
    return jsonify(crawler.get_status())


@app.route('/api/extract-cids', methods=['POST'])
def api_extract_cids():
    """从URL/文本中提取CID（IF-DSS 4.1.1）"""
    text = request.form.get('url_text', '')
    cids = _forum_scanner.extract_cids(text)

    if cids:
        html = f'<div class="alert alert-success py-1 px-2 mb-1" style="font-size:12px;">发现 {len(cids)} 个CID</div>'
        html += '<ul class="list-unstyled mb-0">'
        for cid in cids:
            html += (
                f'<li class="mb-1">'
                f'<code style="font-size:11px;">{cid[:30]}...</code> '
                f'<a href="/evidence?target_cid={cid}" '
                f'class="btn btn-sm btn-gold py-0 px-1" style="font-size:11px;">'
                f'<i class="bi bi-send me-1"></i>取证</a>'
                f'</li>'
            )
        html += '</ul>'
    else:
        html = '<div class="alert alert-warning py-1 px-2 mb-0" style="font-size:12px;">未发现CID</div>'

    return html


@app.route('/api/node-info')
def api_node_info():
    """获取本地IPFS节点信息（IF-DSS Node区域）"""
    node_info = _dht_sniffer.get_node_info()
    local_info = _dht_sniffer.inspect_local_node()
    bitswap_stats = _dht_sniffer.get_bitswap_stats()

    return jsonify({
        'node': node_info,
        'local': local_info,
        'bitswap': bitswap_stats,
    })


@app.route('/api/find-providers', methods=['POST'])
def api_find_providers():
    """查找CID提供者（IF-DSS Peer区域）"""
    cid = request.form.get('cid', '').strip()
    if not cid:
        return jsonify({'error': 'CID为空'})

    providers = _dht_sniffer.find_providers(cid, num_providers=10)
    return jsonify({
        'cid': cid,
        'provider_count': len(providers),
        'providers': providers,
    })


# ==================== 证据固定API（IF-DSS: Preservation） ====================

@app.route('/api/collect', methods=['POST'])
def api_collect():
    """执行取证固定"""
    cid = request.form.get('cid', '').strip()
    case_id = request.form.get('case_id', '').strip()
    investigator_id = request.form.get('investigator_id', 'Police_001')

    if not cid:
        return '<div class="alert alert-danger">请输入CID</div>'

    if not case_id:
        case_id = f"CASE-{datetime.now().strftime('%Y-%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    try:
        # 1. 监管链初始化
        custody = ChainOfCustody(case_id=case_id)
        custody.add_record("立案初始化", investigator_id, {"cid": cid})

        # 2. 数据采集（IF-DSS: Gateway区域）
        monitor = GatewayMonitor()
        content = monitor.fetch_cid_content(cid)

        if not content:
            return (
                '<div class="alert alert-danger">'
                '<i class="bi bi-exclamation-triangle me-1"></i>'
                '无法从IPFS网络获取该CID内容，请检查CID或稍后重试。'
                '</div>'
            )

        custody.add_record("数据采集", investigator_id, {
            "bytes_downloaded": len(content)
        })

        # 3. 内容分析（IF-DSS: Examination）
        analyzer = ContentAnalyzer()
        analysis_results = analyzer.analyze(content)

        custody.add_record("内容审查", "System_Analyzer", {
            "file_type": analysis_results['file_type'],
            "is_illegal": analysis_results['is_illegal']
        })

        # 4. 证据固定（多重哈希 + 证据包完整性哈希）
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

        # 5. 可信时间戳（RFC 3161）
        timestamp_result = stamp_evidence(evidence.hashes['sha256'])
        custody.add_record("可信时间戳", investigator_id, {
            "tsa_server": timestamp_result.get('tsa_server'),
            "success": timestamp_result.get('success'),
        })

        # 6. 报告生成
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
                merkle_root=integrity_proof['integrity_hash'],
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
        return (
            f'<div class="alert alert-danger">'
            f'<i class="bi bi-exclamation-triangle me-1"></i>'
            f'取证过程发生错误: {str(e)}'
            f'</div>'
        )


# ==================== 报告导出 ====================

@app.route('/api/export-pdf', methods=['POST'])
def api_export_pdf():
    """导出PDF取证报告"""
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
    """历史记录表格"""
    db = get_db()
    try:
        records = db.query(EvidenceRecord).order_by(
            EvidenceRecord.created_at.desc()
        ).limit(100).all()
        return render_template('partials/history_table.html', records=records)
    finally:
        db.close()


# ==================== 情报分析API（IF-DSS: Analysis） ====================

@app.route('/api/profile', methods=['POST'])
def api_profile():
    """ID画像分析"""
    platform = request.form.get('platform', '')
    user_id = request.form.get('user_id', '')

    profiler = IDProfiler()
    profiler.add_id_relation(
        "Telegram", "dark_user99", "IPFS_Node", "Peer_X1Y2", 0.9
    )
    profiler.add_id_relation(
        "DarkWebForum", "vendor_99", "Telegram", "dark_user99", 0.8
    )
    profiler.add_id_relation(
        "IPFS_Node", "Peer_X1Y2", "Twitter", "crypto_scam_01", 0.7
    )

    result = profiler.profile_id(platform, user_id)
    return jsonify(result)


# ==================== 预防API（IF-DSS: Prevention） ====================

@app.route('/api/prevent/unpin', methods=['POST'])
def api_unpin():
    """从本地节点unpin内容（IF-DSS 4.4.2）"""
    cid = request.form.get('cid', '').strip()
    if not cid:
        return jsonify({'success': False, 'error': 'CID为空'})

    try:
        resp = requests.post(
            "http://127.0.0.1:5001/api/v0/pin/rm",
            params={'arg': cid},
            timeout=10
        )
        success = resp.status_code == 200
        return jsonify({
            'success': success,
            'action': 'unpin',
            'cid': cid,
            'message': '已从本地节点取消固定' if success else f'操作失败: {resp.status_code}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/prevent/report', methods=['POST'])
def api_abuse_report():
    """生成abuse report文本（IF-DSS 4.4.1）"""
    cid = request.form.get('cid', '').strip()
    reason = request.form.get('reason', '涉嫌违法内容')

    gateway_urls = [
        f"https://ipfs.io/ipfs/{cid}",
        f"https://cloudflare-ipfs.com/ipfs/{cid}",
        f"https://dweb.link/ipfs/{cid}",
    ]

    report_text = f"""=== IPFS内容阻断举报 ===
CID: {cid}
举报原因: {reason}
涉及网关URL:
{chr(10).join('  - ' + u for u in gateway_urls)}

举报提交地址:
  - IPFS官方: https://ipfs.tech/help/
  - Cloudflare: https://www.cloudflare.com/abuse/form
  - Pinata: https://www.pinata.cloud/contact
"""

    return jsonify({
        'cid': cid,
        'report_text': report_text,
        'submit_urls': {
            'ipfs.io': 'https://ipfs.tech/help/',
            'cloudflare': 'https://www.cloudflare.com/abuse/form',
            'pinata': 'https://www.pinata.cloud/contact',
        }
    })


# ==================== 启动 ====================

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("  IPFS取证系统 v2.0 (Flask + IF-DSS)")
    logger.info("  访问: http://localhost:5000")
    logger.info("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)