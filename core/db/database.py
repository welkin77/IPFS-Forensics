"""
数据库连接配置
改动：删除 FastAPI 的 yield 依赖注入，改为普通函数
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./ipfs_forensics.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """获取数据库Session（Flask用法：手动调用，手动关闭）"""
    return SessionLocal()