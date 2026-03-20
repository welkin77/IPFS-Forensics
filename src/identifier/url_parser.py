# src/identifier/url_parser.py

import re
import csv
import os
from dataclasses import dataclass
from typing import List
from ..integrity.hasher import compute_hash

@dataclass
class IdentifiedURL:
    """标识符提取结果（IF-DSS只输出文本文件，这里结构化）"""
    original_url: str
    cid: str = None
    url_type: str = None      # Type1/Type2/Type3
    gateway: str = None
    filename: str = None

# CID正则（直接复用IF-DSS）
CID_REGEX = r"(Qm[1-9A-HJ-NP-Za-km-z]{44}|baf[A-Za-z2-7]{56})"
DNS_REGEX = r"^https?://[a-zA-Z0-9-]+\.on\.fleek\.co"

def extract_cid_from_url(url: str) -> IdentifiedURL:
    """
    增强IF-DSS parse.py：不仅提取CID，还识别URL类型和网关
    
    IF-DSS原始行为：只用正则提取CID，输出到文本文件
    v3增强：结构化输出，识别3种URL类型
    """
    result = IdentifiedURL(original_url=url)
    
    # 提取CID（复用IF-DSS的正则）
    cid_match = re.search(CID_REGEX, url)
    if cid_match:
        result.cid = cid_match.group(1)
    
    # 识别URL类型（IF-DSS未实现，v3新增）
    if result.cid:
        if f"/ipfs/{result.cid}" in url:
            result.url_type = "Type1"  # https://{gateway}/ipfs/{cid}
        elif url.startswith(f"https://{result.cid}."):
            result.url_type = "Type2"  # https://{cid}.{gateway}
        else:
            result.url_type = "Type1"  # 默认
    
    return result

def parse_phishtank_csv(csv_path: str) -> List[IdentifiedURL]:
    """
    重构IF-DSS parse_url()：从PhishTank CSV批量提取
    
    IF-DSS原始：读CSV → 正则匹配 → 写文本文件
    v3改进：返回结构化列表，同时保留文件输出兼容性
    """
    results = []
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.reader(f)
        next(reader)  # 跳过表头（与IF-DSS一致）
        for row in reader:
            if len(row) > 1:
                url = row[1]
                if re.search(CID_REGEX, url):
                    results.append(extract_cid_from_url(url))
    return results

def save_cid_list(results: List[IdentifiedURL], output_path: str):
    """兼容IF-DSS的输出格式"""
    cid_file = os.path.join(output_path, "cid_result.txt")
    with open(cid_file, 'w') as f:
        for r in results:
            if r.cid:
                f.write(r.original_url + '\n')
    return cid_file