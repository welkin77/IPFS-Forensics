# src/utils/ipfs_command.py
"""统一封装ipfs命令调用，处理版本差异"""
import subprocess

def run_ipfs_command(args: list, ipfs_path: str = "ipfs", 
                     timeout: int = 60) -> str:
    """
    Kubo 0.40+ 命令变更适配：
    - dht findprovs → routing findprovs
    - dht findpeer → routing findpeer  
    - object links → dag get
    """
    full_args = [ipfs_path] + args
    result = subprocess.run(
        full_args, capture_output=True, text=True, 
        timeout=timeout
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, full_args, 
            result.stdout, result.stderr
        )
    return result.stdout
