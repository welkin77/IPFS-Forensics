"""
数据采集层
对应设计方案 3.1 节

职责：从多种信源采集IPFS CID线索
- gateway_monitor: 通过IPFS网关下载文件内容（取证固定时使用）
- crawler:         多源情报嗅探引擎（雷达扫描时使用）
- dht_sniffer:     本地IPFS节点DHT/Bitswap底层嗅探
- forum_scanner:   IPFS论坛/Reddit等公开信源扫描
"""

from core.collector.gateway_monitor import GatewayMonitor
from core.collector.crawler import IntelligenceCrawler

__all__ = ['GatewayMonitor', 'IntelligenceCrawler']