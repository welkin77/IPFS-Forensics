"""
可信时间戳模块
位置: core/evidence/timestamp.py

遵循 RFC 3161 标准，对接免费的时间戳服务器
设计方案 3.2.3 对应实现
"""

import hashlib
import base64
import logging
from datetime import datetime
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class TimestampModule:
    """
    RFC 3161 可信时间戳
    
    支持的免费TSA服务器：
    - FreeTSA (freetsa.org)
    - Comodo/Sectigo
    - DigiCert
    """

    # 免费可用的 TSA 服务器列表（按可靠性排序）
    TSA_SERVERS = [
        {
            'name': 'FreeTSA',
            'url': 'https://freetsa.org/tsr',
            'hash_algo': 'sha256'
        },
        {
            'name': 'Sectigo',
            'url': 'http://timestamp.sectigo.com',
            'hash_algo': 'sha256'
        },
        {
            'name': 'DigiCert',
            'url': 'http://timestamp.digicert.com',
            'hash_algo': 'sha256'
        },
    ]

    def __init__(self, tsa_url: str = None):
        """
        Args:
            tsa_url: 指定TSA服务器URL，为空则使用默认列表轮询
        """
        self.tsa_url = tsa_url

    def request_timestamp(self, data_hash: str) -> dict:
        """
        向时间戳服务器请求时间戳令牌
        
        Args:
            data_hash: 待加盖时间戳的数据SHA-256哈希值（十六进制字符串）
        
        Returns:
            {
                'success': bool,
                'tsa_server': str,
                'timestamp_token': str (base64编码),
                'request_time': str (ISO格式),
                'hash_algorithm': str,
                'original_hash': str
            }
        """
        hash_bytes = bytes.fromhex(data_hash)
        
        # 构建 RFC 3161 TimeStampReq
        ts_request = self._build_ts_request(hash_bytes)
        
        # 尝试请求
        servers = (
            [{'name': 'custom', 'url': self.tsa_url, 'hash_algo': 'sha256'}]
            if self.tsa_url
            else self.TSA_SERVERS
        )
        
        for server in servers:
            try:
                logger.info(f"[时间戳] 正在请求 {server['name']} ({server['url']})...")
                
                response = requests.post(
                    server['url'],
                    data=ts_request,
                    headers={'Content-Type': 'application/timestamp-query'},
                    timeout=15
                )
                
                if response.status_code == 200:
                    token_b64 = base64.b64encode(response.content).decode('utf-8')
                    
                    result = {
                        'success': True,
                        'tsa_server': server['name'],
                        'tsa_url': server['url'],
                        'timestamp_token': token_b64,
                        'request_time': datetime.utcnow().isoformat() + 'Z',
                        'hash_algorithm': 'sha256',
                        'original_hash': data_hash,
                        'token_size_bytes': len(response.content)
                    }
                    
                    logger.info(
                        f"[时间戳] 成功！服务器: {server['name']}, "
                        f"令牌大小: {len(response.content)} bytes"
                    )
                    return result
                else:
                    logger.warning(
                        f"[时间戳] {server['name']} 返回 {response.status_code}"
                    )
                    
            except requests.exceptions.Timeout:
                logger.warning(f"[时间戳] {server['name']} 超时")
            except requests.exceptions.ConnectionError:
                logger.warning(f"[时间戳] {server['name']} 连接失败")
            except Exception as e:
                logger.warning(f"[时间戳] {server['name']} 异常: {e}")
        
        # 所有服务器都失败时，记录本地时间戳（降级方案）
        logger.error("[时间戳] 所有TSA服务器均不可用，使用本地时间戳（降级）")
        return {
            'success': False,
            'tsa_server': 'LOCAL_FALLBACK',
            'tsa_url': 'N/A',
            'timestamp_token': '',
            'request_time': datetime.utcnow().isoformat() + 'Z',
            'hash_algorithm': 'sha256',
            'original_hash': data_hash,
            'token_size_bytes': 0,
            'warning': '未能获取可信时间戳，使用本地系统时间'
        }

    def _build_ts_request(self, hash_bytes: bytes) -> bytes:
        """
        构建 RFC 3161 TimeStampReq（简化版）
        
        完整的 ASN.1 DER 编码的 TimeStampReq 结构：
        TimeStampReq ::= SEQUENCE {
            version        INTEGER { v1(1) },
            messageImprint MessageImprint,
            nonce          INTEGER OPTIONAL
        }
        MessageImprint ::= SEQUENCE {
            hashAlgorithm  AlgorithmIdentifier,
            hashedMessage  OCTET STRING
        }
        """
        # SHA-256 的 OID: 2.16.840.1.101.3.4.2.1
        sha256_oid = bytes([
            0x30, 0x0d,  # SEQUENCE
            0x06, 0x09,  # OID
            0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01,
            0x05, 0x00   # NULL
        ])
        
        # MessageImprint
        hash_octet = bytes([0x04, len(hash_bytes)]) + hash_bytes
        msg_imprint_body = sha256_oid + hash_octet
        msg_imprint = bytes([0x30, len(msg_imprint_body)]) + msg_imprint_body
        
        # Version (v1 = 1)
        version = bytes([0x02, 0x01, 0x01])
        
        # certReq BOOLEAN TRUE (请求返回证书)
        cert_req = bytes([0x01, 0x01, 0xff])
        
        # 完整请求
        body = version + msg_imprint + cert_req
        ts_req = bytes([0x30, len(body)]) + body
        
        return ts_req

    def verify_timestamp(self, timestamp_result: dict) -> dict:
        """
        验证时间戳令牌（基础验证）
        
        Args:
            timestamp_result: request_timestamp 返回的字典
        
        Returns:
            验证结果
        """
        if not timestamp_result.get('success'):
            return {
                'valid': False,
                'reason': '时间戳令牌获取失败',
                'timestamp_result': timestamp_result
            }
        
        token_b64 = timestamp_result.get('timestamp_token', '')
        if not token_b64:
            return {'valid': False, 'reason': '令牌为空'}
        
        try:
            token_bytes = base64.b64decode(token_b64)
            
            # 基础结构验证：检查是否为有效的 ASN.1 DER
            if len(token_bytes) < 10:
                return {'valid': False, 'reason': '令牌数据过短'}
            
            # 检查 SEQUENCE 标签
            if token_bytes[0] != 0x30:
                return {'valid': False, 'reason': '非有效ASN.1结构'}
            
            return {
                'valid': True,
                'tsa_server': timestamp_result['tsa_server'],
                'request_time': timestamp_result['request_time'],
                'original_hash': timestamp_result['original_hash'],
                'token_size': len(token_bytes)
            }
            
        except Exception as e:
            return {'valid': False, 'reason': f'验证异常: {e}'}


# 便捷函数
def stamp_evidence(evidence_hash: str) -> dict:
    """
    一键为证据哈希加盖可信时间戳
    
    Args:
        evidence_hash: 证据包的SHA-256哈希
    
    Returns:
        时间戳结果
    """
    ts = TimestampModule()
    return ts.request_timestamp(evidence_hash)