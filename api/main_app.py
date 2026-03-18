import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import evidence, analysis, clues

# 初始化 FastAPI 应用
app = FastAPI(
    title="IPFS 去中心化非法内容取证系统 API",
    description="提供基于多重哈希、默克尔树和区块链锚定的电子数据取证接口",
    version="1.0.0"
)

# 配置 CORS 跨域（允许 Vue3 前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 实际部署时应改为 Vue 的具体域名，如 ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由模块
app.include_router(evidence.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(clues.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "IPFS Forensics API is running. Visit /docs for Swagger UI."}

if __name__ == "__main__":
    # 使用 Uvicorn 启动服务器
    # 注意：这里的 "api.main_app:app" 对应 文件夹名.文件名:FastAPI实例名
    uvicorn.run("api.main_app:app", host="0.0.0.0", port=8000, reload=True)