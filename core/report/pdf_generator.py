"""
PDF取证报告生成器
位置: core/report/pdf_generator.py

生成符合 GA/T 2343-2025 格式的 PDF 取证报告
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 尝试导入 reportlab，没有则降级
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    logger.warning("未安装 reportlab，PDF生成功能不可用。pip install reportlab")


class PDFReportGenerator:
    """
    司法取证报告 PDF 生成器
    符合 GA/T 2343-2025《法庭科学 电子数据保全文件技术要求》
    """

    # 报告输出目录
    OUTPUT_DIR = "reports"

    def __init__(self):
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
        self._font_registered = False

    def _register_chinese_font(self, c):
        """注册中文字体"""
        if self._font_registered:
            return

        # 尝试常见中文字体路径
        font_paths = [
            'C:/Windows/Fonts/simhei.ttf',        # Windows 黑体
            'C:/Windows/Fonts/simsun.ttc',         # Windows 宋体
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',  # Linux
            '/System/Library/Fonts/PingFang.ttc',  # macOS
        ]

        for path in font_paths:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont('ChineseFont', path))
                    self._font_registered = True
                    return
                except Exception:
                    continue

        logger.warning("未找到中文字体，PDF将使用英文字体")

    def generate(self, report_data: Dict[str, Any], case_id: str = None) -> str:
        """
        生成 PDF 取证报告
        
        Args:
            report_data: 完整的取证报告数据（与前端 ForensicReport 组件相同的数据结构）
            case_id: 案件编号
        
        Returns:
            PDF文件路径
        """
        if not HAS_REPORTLAB:
            raise RuntimeError("请安装 reportlab: pip install reportlab")

        case_id = case_id or report_data.get('case_info', {}).get('case_id', 'UNKNOWN')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"取证报告_{case_id}_{timestamp}.pdf"
        filepath = os.path.join(self.OUTPUT_DIR, filename)

        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4

        self._register_chinese_font(c)
        font_name = 'ChineseFont' if self._font_registered else 'Helvetica'
        font_bold = 'ChineseFont' if self._font_registered else 'Helvetica-Bold'

        y = height - 40 * mm

        # ==================== 标题 ====================
        c.setFont(font_bold, 18)
        c.drawCentredString(width / 2, y, "电子数据取证报告")
        y -= 8 * mm

        c.setFont(font_name, 9)
        c.drawCentredString(width / 2, y, "（依据 GA/T 2343-2025 标准生成）")
        y -= 12 * mm

        # ==================== 案件信息 ====================
        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "一、案件信息")
        y -= 7 * mm

        case_info = report_data.get('case_info', {})
        evidence_summary = report_data.get('evidence_summary', {})

        info_lines = [
            f"案件编号：{case_info.get('case_id', case_id)}",
            f"案件名称：{case_info.get('case_name', 'IPFS非法内容取证')}",
            f"取证时间：{case_info.get('generation_time', datetime.now().isoformat())}",
            f"取证人员：{evidence_summary.get('investigator', 'N/A')}",
            f"取证工具：IPFS取证系统 v2.0",
        ]

        c.setFont(font_name, 10)
        for line in info_lines:
            c.drawString(30 * mm, y, line)
            y -= 5.5 * mm

        y -= 5 * mm

        # ==================== 证据来源 ====================
        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "二、电子数据来源")
        y -= 7 * mm

        c.setFont(font_name, 10)
        source_lines = [
            f"目标 CID：{evidence_summary.get('cid', 'N/A')}",
            f"来源网关：{evidence_summary.get('source_gateway', 'GatewayMonitor')}",
            f"文件大小：{evidence_summary.get('file_size_bytes', 0)} bytes",
            f"文件类型：{report_data.get('analysis_results', {}).get('file_type', 'N/A')}",
        ]
        for line in source_lines:
            c.drawString(30 * mm, y, line)
            y -= 5.5 * mm

        y -= 5 * mm

        # ==================== 完整性校验 ====================
        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "三、完整性校验值")
        y -= 7 * mm

        c.setFont(font_name, 10)
        hashes = evidence_summary.get('hash_values', {})
        for algo, value in hashes.items():
            label = algo.upper()
            c.drawString(30 * mm, y, f"{label}：")
            y -= 5 * mm
            # 哈希值可能很长，用等宽字体
            c.setFont('Courier', 8)
            c.drawString(35 * mm, y, str(value))
            c.setFont(font_name, 10)
            y -= 6 * mm

        y -= 3 * mm

        # ==================== 可信时间戳 ====================
        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "四、可信时间戳")
        y -= 7 * mm

        ts = report_data.get('timestamp', {})
        c.setFont(font_name, 10)
        if ts.get('success'):
            ts_lines = [
                f"时间戳服务器：{ts.get('tsa_server', 'N/A')}",
                f"请求时间：{ts.get('request_time', 'N/A')}",
                f"令牌大小：{ts.get('token_size_bytes', 0)} bytes",
                f"状态：已加盖可信时间戳",
            ]
        else:
            ts_lines = [
                f"状态：{ts.get('warning', '使用本地系统时间')}",
                f"记录时间：{ts.get('request_time', datetime.now().isoformat())}",
            ]
        for line in ts_lines:
            c.drawString(30 * mm, y, line)
            y -= 5.5 * mm

        y -= 5 * mm

        # ==================== 内容分析 ====================
        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "五、内容分析结果")
        y -= 7 * mm

        analysis = report_data.get('analysis_results', {})
        c.setFont(font_name, 10)

        is_illegal = analysis.get('is_illegal', False)
        c.drawString(30 * mm, y, f"是否涉嫌违法：{'是' if is_illegal else '否'}")
        y -= 5.5 * mm

        if is_illegal:
            keywords = analysis.get('matched_keywords', [])
            c.drawString(30 * mm, y, f"命中关键词：{', '.join(keywords)}")
            y -= 5.5 * mm

        extracted = analysis.get('extracted_text', '')
        if extracted:
            c.drawString(30 * mm, y, "提取文本摘要：")
            y -= 5 * mm
            # 截断长文本
            for chunk in [extracted[i:i+60] for i in range(0, min(len(extracted), 300), 60)]:
                c.setFont('Courier', 8)
                c.drawString(35 * mm, y, chunk)
                y -= 4 * mm
            c.setFont(font_name, 10)

        y -= 5 * mm

        # ==================== 监管链 ====================
        if y < 120 * mm:
            c.showPage()
            y = height - 30 * mm

        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "六、监管链记录 (Chain of Custody)")
        y -= 7 * mm

        chain = report_data.get('chain_of_custody', [])
        c.setFont(font_name, 9)
        for record in chain:
            action = record.get('action', 'N/A')
            operator = record.get('operator', 'N/A')
            ts_val = record.get('timestamp', 'N/A')
            rhash = record.get('record_hash', '')[:16]

            line = f"[{ts_val}] {action} — 操作人: {operator} — 审计哈希: {rhash}..."
            c.drawString(30 * mm, y, line)
            y -= 5 * mm

            if y < 30 * mm:
                c.showPage()
                y = height - 30 * mm

        y -= 8 * mm

        # ==================== 合规性声明 ====================
        if y < 60 * mm:
            c.showPage()
            y = height - 30 * mm

        c.setFont(font_bold, 12)
        c.drawString(25 * mm, y, "七、合规性声明")
        y -= 7 * mm

        c.setFont(font_name, 9)
        declarations = [
            "1. 本报告依据 GA/T 2343-2025《法庭科学 电子数据保全文件技术要求》生成。",
            "2. 电子数据的提取过程符合《关于办理刑事案件收集提取和审查判断电子数据若干问题的规定》。",
            "3. 完整性校验采用多重哈希算法（SHA-256、SHA-512、Keccak-256），确保数据未被篡改。",
            "4. 监管链记录采用哈希链结构，任何篡改均可被检测。",
            "5. 取证过程中遵循 ISO/IEC 27037 及 ACPO 电子证据处理原则。",
        ]
        for decl in declarations:
            c.drawString(30 * mm, y, decl)
            y -= 5 * mm

        y -= 10 * mm

        # 签名区
        c.setFont(font_name, 10)
        c.drawString(30 * mm, y, f"报告生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
        y -= 8 * mm
        c.drawString(30 * mm, y, "取证人员签名：________________")
        y -= 8 * mm
        c.drawString(30 * mm, y, "审核人员签名：________________")

        # 页脚
        c.setFont(font_name, 8)
        c.drawCentredString(width / 2, 15 * mm, "IPFS去中心化非法内容取证系统 — 本报告由系统自动生成")

        c.save()
        logger.info(f"[PDF报告] 已生成: {filepath}")
        return filepath