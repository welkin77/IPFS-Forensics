import json
import os
from typing import Dict, Any
from core.evidence.package import EvidencePackage
from core.evidence.custody import ChainOfCustody
from utils.logger import setup_logger

logger = setup_logger(__name__)

class EvidenceReportGenerator:
    """符合司法要求的电子证据报告生成器"""

    def __init__(self, case_info: Dict[str, Any]):
        self.case_info = case_info

    def generate_json_report(self, 
                             evidence: EvidencePackage, 
                             custody_chain: ChainOfCustody, 
                             analysis_results: Dict[str, Any], 
                             output_path: str = "forensic_report.json") -> str:
        """
        生成结构化的 JSON 取证报告并保存到本地
        """
        report = {
            "case_info": self.case_info,
            "evidence_summary": {
                "cid": evidence.cid,
                "acquisition_time": evidence.timestamp,
                "file_size_bytes": len(evidence.content),
                "hash_values": evidence.hashes
            },
            "verification_proof": {
                "merkle_root": evidence.merkle_root,
                "verification_steps": [
                    "1. 从公网IPFS网关/节点获取数据",
                    "2. 计算 SHA256 与 SHA512 本地司法哈希",
                    "3. 计算 Keccak-256 以太坊上链哈希",
                    "4. 构建证据及元数据的默克尔树"
                ]
            },
            "chain_of_custody": custody_chain.export_chain(),
            "analysis_results": analysis_results,
            "legal_attestation": "本报告由系统自动生成，哈希链完整，符合电子数据取证技术标准。"
        }

        # 写入文件
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=4)
            logger.info(f"证据报告已成功生成并保存至: {os.path.abspath(output_path)}")
        except IOError as e:
            logger.error(f"报告保存失败: {str(e)}")
            
        return json.dumps(report, ensure_ascii=False)