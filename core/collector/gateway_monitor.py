import requests
import urllib3
from typing import Optional, List
from utils.logger import setup_logger

# 禁用 urllib3 的 InsecureRequestWarning 警告 (对应日志里的刷屏报错)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = setup_logger(__name__)

class GatewayMonitor:
    """公共/本地网关监控与司法级下载模块"""
    
    def __init__(self):
        self.gateways: List[str] = [
            'http://127.0.0.1:8080/ipfs/',      # 首选：IPFS Desktop 提供的本地极速网关
            'https://dweb.link/ipfs/',          # 备选1：Protocol Labs 官方优化的网关
            'https://ipfs.io/ipfs/',            # 备选2：官方基础网关
            'https://gateway.pinata.cloud/ipfs/'# 备选3：Pinata
        ]
        
        # P2P 网络寻址非常慢，将超时时间放宽至 60 秒
        self.timeout: int = 60
        
        # 证据保全限制：对于超大文件，只下载前 50MB 用于哈希计算和内容审查
        # (突破毕设限制的实战设计：防止取证服务器被 100GB 的恶意 CID 挤爆内存)
        self.max_file_size = 50 * 1024 * 1024 

        # 如果你在国内，公共网关需要代理。请根据你的 Clash/V2ray 端口修改
        # 这种写法比 os.environ 更加安全，不会污染全局环境
        self.proxy_url = "http://127.0.0.1:7890" 
        self.proxies = {
            "http": self.proxy_url,
            "https": self.proxy_url
        }

    def fetch_cid_content(self, cid: str) -> Optional[bytes]:
        """流式下载 CID 内容，带有大小限制和智能代理"""
        
        for gateway in self.gateways:
            url = f"{gateway}{cid}"
            
            # 智能判断：如果是本地网关，绝不走代理；如果是公共网关，则挂载代理
            use_proxy = None if "127.0.0.1" in gateway or "localhost" in gateway else self.proxies

            try:
                logger.info(f"正在尝试从网关获取数据: {url}")
                
                # 开启 stream=True 进行流式下载，避免内存爆炸
                response = requests.get(
                    url, 
                    timeout=self.timeout, 
                    verify=False, 
                    proxies=use_proxy,
                    stream=True 
                )
                
                if response.status_code == 200:
                    content_bytes = bytearray()
                    downloaded_size = 0
                    
                    # 以 128KB 为一个块进行读取
                    for chunk in response.iter_content(chunk_size=128 * 1024):
                        if chunk:
                            content_bytes.extend(chunk)
                            downloaded_size += len(chunk)
                            
                            # 触发司法熔断：文件过大，截断下载
                            if downloaded_size >= self.max_file_size:
                                logger.warning(f"CID {cid} 体积过大，已触发司法截断 (仅保留前 {self.max_file_size/1024/1024}MB)")
                                break
                                
                    logger.info(f"成功从 {gateway} 获取 CID: {cid} 的内容 (大小: {downloaded_size} 字节)")
                    return bytes(content_bytes)
                    
                elif response.status_code == 504:
                    logger.warning(f"网关 {gateway} 寻址超时 (504)，该 CID 可能处于冷门状态或死链。")
                else:
                    logger.warning(f"网关 {gateway} 响应异常，状态码: {response.status_code}")
                    
            except requests.exceptions.ReadTimeout:
                logger.warning(f"网关 {gateway} 请求超时 (>{self.timeout}s)，跳过。")
            except requests.exceptions.ProxyError:
                logger.error(f"网关 {gateway} 代理连接失败，请检查 {self.proxy_url} 是否正常运行！")
            except requests.exceptions.RequestException as e:
                logger.error(f"网关 {gateway} 请求异常: {type(e).__name__}")
                
        logger.error(f"证据固定失败：无法从任何已知网关获取 CID [{cid}] 的内容。该节点可能已下线。")
        return None