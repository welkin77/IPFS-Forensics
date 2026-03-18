import io
import filetype
import jieba
import pytesseract
from PIL import Image
from typing import Dict, Any, List
from utils.logger import setup_logger

logger = setup_logger(__name__)

# 如果你是 Windows 用户，请取消下面这行的注释，并修改为你的实际安装路径！
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class ContentAnalyzer:
    """多媒体内容解析与敏感信息审计引擎"""

    def __init__(self):
        # 模拟公安系统的“违规特征词库”
        self.sensitive_keywords = [
            "洗钱", "诈骗", "赌博", "色情", "代开", "枪支", "毒品", "VPN", "翻墙"
        ]
        
    def analyze(self, content_bytes: bytes) -> Dict[str, Any]:
        """对下载的二进制内容进行全面解析"""
        result = {
            "file_type": "unknown",
            "is_illegal": False,
            "risk_level": "low",
            "matched_keywords": [],
            "analysis_method": "none",
            "extracted_text": ""
        }

        if not content_bytes:
            return result

        # 1. 精准识别文件类型 (基于 Magic Numbers)
        kind = filetype.guess(content_bytes)
        if kind is None:
            # 可能是纯文本
            result["file_type"] = "text/plain"
            text_content = self._extract_text_from_bytes(content_bytes)
            result["analysis_method"] = "NLP/Jieba"
        else:
            result["file_type"] = kind.mime
            
            # 2. 如果是图片，调用 Pillow 和 Tesseract OCR
            if kind.mime.startswith('image/'):
                logger.info(f"检测到图片文件 ({kind.mime})，启动 OCR 解析...")
                text_content = self._extract_text_from_image(content_bytes)
                result["analysis_method"] = "Pillow + Tesseract OCR"
            # 3. 如果是其他类型（PDF, 视频等），目前仅标记类型
            else:
                text_content = ""
                result["analysis_method"] = "File Header Analysis"

        result["extracted_text"] = text_content[:200] + ("..." if len(text_content) > 200 else "") # 只保留摘要

        # 4. 使用 Jieba 分词并进行敏感词碰撞
        if text_content:
            words = list(jieba.cut(text_content))
            matched = list(set(words) & set(self.sensitive_keywords))
            
            if matched:
                result["is_illegal"] = True
                result["risk_level"] = "high"
                result["matched_keywords"] = matched
                logger.warning(f"⚠️ 发现非法内容！命中特征词: {matched}")
            else:
                logger.info("内容审核通过，未发现敏感词。")

        return result

    def _extract_text_from_bytes(self, content: bytes) -> str:
        try:
            return content.decode('utf-8', errors='ignore')
        except Exception:
            return ""

    def _extract_text_from_image(self, content: bytes) -> str:
        try:
            image = Image.open(io.BytesIO(content))
            # 设置 OCR 语言为中文和英文
            text = pytesseract.image_to_string(image, lang='chi_sim+eng')
            return text.strip().replace('\n', ' ')
        except Exception as e:
            logger.error(f"OCR 解析失败: {e}")
            return ""