from fastapi import APIRouter, HTTPException
from api.schemas import ProfileRequest, ProfileResponse
from core.analysis.id_profiler import IDProfiler
from utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/analysis", tags=["情报分析 (Analysis)"])

@router.post("/profile", response_model=ProfileResponse)
async def generate_id_profile(request: ProfileRequest):
    """
    根据前端传入的平台和用户 ID，生成虚拟身份跨平台关联画像。
    """
    logger.info(f"收到画像分析请求: {request.platform}:{request.user_id}")
    
    profiler = IDProfiler()
    # TODO: 实际项目中这里应从图数据库(如Neo4j)或关系型数据库中读取边数据
    # 这里我们注入一些模拟数据供前端渲染关系图测试
    profiler.add_id_relation("Telegram", "dark_user99", "IPFS_Node", "Peer_X1Y2", 0.9)
    profiler.add_id_relation("DarkWebForum", "vendor_99", "Telegram", "dark_user99", 0.8)
    profiler.add_id_relation("IPFS_Node", "Peer_X1Y2", "Twitter", "crypto_scam_01", 0.7)
    
    profile_result = profiler.profile_id(request.platform, request.user_id)
    
    if 'error' in profile_result:
        raise HTTPException(status_code=404, detail="未找到该用户的关联画像数据")
        
    return ProfileResponse(
        seed_node=profile_result['seed_node'],
        related_nodes=profile_result['related_nodes'],
        node_count=profile_result['node_count'],
        edge_count=profile_result['edge_count']
    )