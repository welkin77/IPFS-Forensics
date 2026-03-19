import uvicorn
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import evidence, analysis, clues
from core.collector.dht_probe import DHTProbe
from core.collector.osint_monitor import (
    OSINTManager, RedditMonitor, TelegramMonitor, DarkwebMonitor
)
from core.analysis.anomaly_detector import AnomalyDetector
from utils.error_handler import (
    setup_exception_handlers, error_tracker,
    ForensicsBaseError
)

logger = logging.getLogger(__name__)

# 初始化 FastAPI 应用
app = FastAPI(
    title="IPFS 去中心化非法内容取证系统 API",
    description="提供基于多重哈希、默克尔树和区块链锚定的电子数据取证接口",
    version="1.0.0"
)

# 设置全局异常处理
setup_exception_handlers(app)

# 初始化新模块
dht_probe = DHTProbe()
osint_manager = OSINTManager()
anomaly_detector = AnomalyDetector()

# 初始化OSINT（Reddit无需API key，可直接启动）
reddit_monitor = RedditMonitor(
    subreddits=['ipfs', 'filecoin', 'web3', 'darknet'],
    poll_interval=120
)
osint_manager.add_monitor('reddit', reddit_monitor)

# 连接OSINT到异常检测
async def _on_cid_discovered(mention):
    anomaly_detector.record_event(
        cid=mention.cid,
        platform=mention.platform.value,
        author_id=mention.author_id,
        timestamp=mention.timestamp
    )
    alerts = anomaly_detector.analyze(mention.cid)
    for alert in alerts:
        logger.warning(f"异常告警: {alert.description}")

osint_manager.on_cid_found(_on_cid_discovered)

# ============================================================
# DHT探测路由
# ============================================================

@app.post("/api/v1/dht/crawl")
async def start_dht_crawl():
    """启动DHT网络爬行"""
    stats = await dht_probe.crawl_network()
    return stats


@app.get("/api/v1/dht/stats")
async def get_dht_stats():
    """获取DHT探测统计"""
    return dht_probe.get_statistics()


@app.get("/api/v1/dht/providers/{cid}")
async def find_cid_providers(cid: str, deep: bool = False):
    """查找CID提供者"""
    if deep:
        record = await dht_probe.find_providers_deep(cid)
    else:
        record = await dht_probe.find_providers(cid)
    return record.to_dict()


@app.post("/api/v1/dht/watch/{cid}")
async def watch_cid(cid: str):
    """添加CID到监控列表"""
    await dht_probe.watch_cid(cid)
    return {"status": "ok", "message": f"CID {cid} 已添加监控"}


@app.get("/api/v1/dht/network-graph")
async def get_network_graph():
    """获取网络拓扑图数据"""
    return dht_probe.export_network_graph()


# ============================================================
# OSINT监控路由
# ============================================================

@app.get("/api/v1/osint/stats")
async def get_osint_stats():
    """获取OSINT监控统计"""
    return osint_manager.get_all_stats()


@app.get("/api/v1/osint/mentions/{cid}")
async def get_cid_mentions(cid: str):
    """获取CID的所有公开提及"""
    return osint_manager.get_cid_mentions(cid)


@app.get("/api/v1/osint/author/{author_id}")
async def get_author_activity(author_id: str):
    """获取作者活动"""
    return osint_manager.get_author_activity(author_id)


@app.get("/api/v1/osint/high-risk")
async def get_high_risk(threshold: float = 0.7):
    """获取高风险CID提及"""
    return osint_manager.get_high_risk_mentions(threshold)


@app.get("/api/v1/osint/cross-platform")
async def get_cross_platform():
    """获取跨平台传播的CID"""
    return osint_manager.get_cross_platform_cids()


# ============================================================
# 异常检测路由
# ============================================================

@app.get("/api/v1/anomaly/analyze/{cid}")
async def analyze_cid_anomaly(cid: str):
    """分析CID异常"""
    alerts = anomaly_detector.analyze(cid)
    return [a.to_dict() for a in alerts]


@app.get("/api/v1/anomaly/alerts")
async def get_anomaly_alerts(
    level: str = None,
    limit: int = 100,
    unacknowledged_only: bool = False
):
    """获取异常告警"""
    from core.analysis.anomaly_detector import AlertLevel
    alert_level = AlertLevel(level) if level else None
    return anomaly_detector.get_alerts(
        level=alert_level, limit=limit,
        unacknowledged_only=unacknowledged_only
    )


@app.post("/api/v1/anomaly/alerts/{alert_id}/acknowledge")
async def acknowledge_anomaly_alert(alert_id: str):
    """确认告警"""
    return {"success": anomaly_detector.acknowledge_alert(alert_id)}


@app.get("/api/v1/anomaly/risk/{cid}")
async def get_cid_risk(cid: str):
    """获取CID风险评分"""
    return anomaly_detector.get_cid_risk_score(cid)


@app.get("/api/v1/anomaly/stats")
async def get_anomaly_stats():
    """异常检测统计"""
    return anomaly_detector.get_statistics()


# ============================================================
# 系统状态路由
# ============================================================

@app.get("/api/v1/system/health")
async def health_check():
    """系统健康检查"""
    return {
        'status': 'healthy',
        'dht': dht_probe.get_statistics(),
        'osint': osint_manager.get_all_stats(),
        'anomaly': anomaly_detector.get_statistics(),
        'errors': error_tracker.get_stats()
    }


@app.get("/api/v1/system/errors")
async def get_system_errors(limit: int = 50):
    """系统错误日志"""
    return error_tracker.get_recent(limit)

# 配置 CORS 跨域（允许 Vue3 前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 实际部署时应改为 Vue 的具体域名，如 ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由模块
app.include_router(evidence.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(clues.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "IPFS Forensics API is running. Visit /docs for Swagger UI."}

if __name__ == "__main__":
    # 使用 Uvicorn 启动服务器
    # 注意：这里的 "api.main_app:app" 对应 文件夹名.文件名:FastAPI实例名
    uvicorn.run("api.main_app:app", host="0.0.0.0", port=8000, reload=True)