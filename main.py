from core.collector.gateway_monitor import GatewayMonitor
from core.evidence.package import EvidencePackage
from core.evidence.custody import ChainOfCustody
from core.analysis.id_profiler import IDProfiler
from core.report.generator import EvidenceReportGenerator
from utils.logger import setup_logger

logger = setup_logger("Main")

def run_forensics_workflow():
    # --- 初始化基础信息 ---
    target_cid = "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"
    investigator_id = "Police_001_Sys"
    case_id = "CASE-2024-IPFS-001"
    
    # 实例化监管链
    custody = ChainOfCustody(case_id=case_id)
    custody.add_record("立案初始化", investigator_id, {"case_id": case_id, "target_cid": target_cid})

    # === 阶段 1: 数据采集 ===
    logger.info("=== 阶段 1: 数据采集 ===")
    monitor = GatewayMonitor()
    content = monitor.fetch_cid_content(target_cid)
    
    if not content:
        logger.error("取证终止：无法获取文件内容")
        return
        
    custody.add_record("数据采集", investigator_id, {"source": "GatewayMonitor", "bytes_downloaded": len(content)})

    # === 阶段 2: 证据固定 ===
    logger.info("=== 阶段 2: 证据固定 ===")
    metadata = {
        "investigator": investigator_id,
        "tool": "IPFS_Forensics_V1.1",
        "case_number": case_id
    }
    
    evidence = EvidencePackage(cid=target_cid, content=content, metadata=metadata)
    merkle_proof = evidence.build_merkle_proof()
    
    custody.add_record("证据固定", "System_Hasher", {
        "sha256": evidence.hashes['sha256'],
        "merkle_root": merkle_proof['merkle_root']
    })
    
    logger.info(f"证据固定完成！Merkle Root: {merkle_proof['merkle_root']}")

    # === 阶段 3: 情报分析 ===
    logger.info("=== 阶段 3: 情报分析 ===")
    profiler = IDProfiler()
    profiler.add_id_relation("Telegram", "dark_user99", "IPFS_Node", "Peer_X1Y2", 0.9)
    profiler.add_id_relation("DarkWebForum", "vendor_99", "Telegram", "dark_user99", 0.8)
    
    profile_result = profiler.profile_id("Telegram", "dark_user99")
    
    custody.add_record("情报分析", "System_Profiler", {"seed_id": "Telegram:dark_user99", "found_nodes": profile_result.get('node_count')})
    logger.info(f"嫌疑人画像结果生成完成。")

    # === 阶段 4: 报告生成 ===
    logger.info("=== 阶段 4: 证据报告生成 ===")
    case_info = {
        "case_id": case_id,
        "case_name": "非法IPFS文件传播溯源案",
        "generation_time": evidence.timestamp
    }
    
    report_gen = EvidenceReportGenerator(case_info)
    # 这将在你的项目根目录生成一个 forensic_report.json 文件
    report_gen.generate_json_report(evidence, custody, profile_result)

if __name__ == "__main__":
    run_forensics_workflow()