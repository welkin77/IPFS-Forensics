import networkx as nx
from typing import Dict, Any, List
from utils.logger import setup_logger

logger = setup_logger(__name__)

class IDProfiler:
    """跨平台ID虚拟身份画像引擎"""

    def __init__(self):
        self.graph = nx.Graph()

    def add_id_relation(self, platform_a: str, id_a: str, platform_b: str, id_b: str, confidence: float):
        """
        添加两个账号ID之间的关联边
        """
        node_a = f"{platform_a}:{id_a}"
        node_b = f"{platform_b}:{id_b}"
        self.graph.add_edge(node_a, node_b, weight=confidence)
        logger.info(f"添加关联: {node_a} <-> {node_b} (置信度: {confidence})")

    def profile_id(self, platform: str, seed_id: str) -> Dict[str, Any]:
        """
        基于种子ID生成关联画像
        """
        target_node = f"{platform}:{seed_id}"
        
        if target_node not in self.graph:
            logger.warning(f"图中未找到节点: {target_node}")
            return {'error': 'Node not found'}

        # 广度优先搜索，寻找2度以内的关联节点
        related_nodes = nx.ego_graph(self.graph, target_node, radius=2)
        
        profile = {
            'seed_node': target_node,
            'related_nodes': list(related_nodes.nodes()),
            'node_count': related_nodes.number_of_nodes(),
            'edge_count': related_nodes.number_of_edges()
        }
        logger.info(f"生成画像成功: {target_node} 包含 {profile['node_count']} 个关联节点")
        return profile