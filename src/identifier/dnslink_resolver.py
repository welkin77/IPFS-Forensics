# src/identifier/dnslink_resolver.py
"""
重构自 IF-DSS dnslink.py
改进：用dnspython替代subprocess调用dig（跨平台兼容）
"""

import json
import os

try:
    import dns.resolver
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False
    import subprocess


def extract_dnslink_domains(file_path: str) -> list:
    """从URL文件提取需要查询DNSLink的域名（复用IF-DSS逻辑）"""
    domains = []
    with open(file_path, 'r') as fd:
        for line in fd:
            line = line.strip()
            if line:
                try:
                    domain = line.split('/')[2]
                    domains.append(f"_dnslink.{domain}")
                except IndexError:
                    continue

    return list(dict.fromkeys(domains))


def query_dnslink_python(domain: str) -> str:
    """用dnspython查询DNSLink TXT记录"""
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if 'dnslink=/ipfs/' in txt:
                cid = txt.split('dnslink=/ipfs/')[1]
                if cid.startswith('Qm'):
                    return cid
    except Exception:
        pass
    return None


def query_dnslink_dig(domain: str, dig_path: str = "dig") -> str:
    """用dig命令查询（IF-DSS原始方式，作为fallback）"""
    try:
        args = [dig_path, '+noall', '+answer', 'TXT', domain]
        output = subprocess.check_output(args)
        output = output.decode('utf-8').split('\n')[0]
        parts = output.split('dnslink=/ipfs/')
        if len(parts) > 1 and parts[1][:2] == "Qm":
            return parts[1].rstrip('"').rstrip()
    except Exception:
        pass
    return None


def dnslink_query(file_path: str, output_path: str, dig_path: str = "dig") -> dict:
    """
    批量查询DNSLink
    优先使用dnspython，不可用时降级到dig命令
    """
    domains = extract_dnslink_domains(file_path)
    result = {}

    for domain in domains:
        cid = None
        if HAS_DNSPYTHON:
            cid = query_dnslink_python(domain)
        else:
            cid = query_dnslink_dig(domain, dig_path)

        if cid:
            result[domain] = cid
            print(f"  {domain} → {cid}")

    output_file = os.path.join(output_path, "dnslink_result.json")
    json.dump(result, open(output_file, "w"), indent=2)
    print(f"[OK] DNSLink results saved to {output_file}")

    return result