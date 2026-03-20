# src/integrity/hasher.py
"""证据完整性（IF-DSS完全没有）"""
import hashlib, json, os
from datetime import datetime

def compute_hash(file_path: str, manifest_path: str = None) -> dict:
    """计算文件的MD5+SHA256双重哈希"""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
            sha256.update(chunk)
    
    entry = {
        "file": file_path,
        "md5": md5.hexdigest(),
        "sha256": sha256.hexdigest(),
        "size": os.path.getsize(file_path),
        "timestamp": datetime.now().isoformat()
    }
    
    if manifest_path:
        manifest = []
        if os.path.exists(manifest_path):
            manifest = json.load(open(manifest_path))
        manifest.append(entry)
        json.dump(manifest, open(manifest_path, 'w'), indent=2)
    
    return entry