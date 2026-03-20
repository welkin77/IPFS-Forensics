# src/utils/config.py
"""全局配置"""

import os

# 默认IPFS路径
DEFAULT_IPFS_BINARY = "ipfs"

# IPFS仓库默认位置
DEFAULT_IPFS_REPO = os.path.expanduser("~/.ipfs")

# 已知的IPFS网关节点ID（复用IF-DSS的黑名单）
GATEWAY_NODE_IDS = [
    "QmQzqxhK82kAmKvARFZSkUVS6fo9sySaiogAnx5EnZ6ZmC",
    "Qma8ddFEQWEU8ijWvdxXm3nxU7oHsRtCykAaVz8WUYhiKn",
    "12D3KooWL4oguAYeRKYL6xv8S5wMwKjLgP78FoNDMECuHY6vAkYH",
    "QmcfJeB3Js1FG7T8YaZATEiaHqNKVdQfybYYkbT1knUswx",
    "12D3KooWPToGJ2YLfYRn6QKQcYT7dwNZD39w3KkMpWjDt8csr8Rf",
    "12D3KooWMkBZYybPgHMr7Se5P2qecu4oz34V1TMgsLPJbNeBCekz",
    "12D3KooWDfrUc9KWYphepLsoGvFYqmHaahjBAKj2iFmY2nFDY2Wy",
]

# CID正则表达式
CID_V0_REGEX = r"Qm[1-9A-HJ-NP-Za-km-z]{44}"
CID_V1_REGEX = r"baf[A-Za-z2-7]{56}"
CID_REGEX = rf"({CID_V0_REGEX}|{CID_V1_REGEX})"