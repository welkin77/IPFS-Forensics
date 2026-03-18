from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 为了本地快速测试，我们先使用 SQLite。
# 等到了服务器部署阶段，只需把下面这行换成 "postgresql://user:password@localhost/ipfs_db" 即可完美切题 PDF！
SQLALCHEMY_DATABASE_URL = "sqlite:///./ipfs_forensics.db"

# 创建数据库引擎 (check_same_thread=False 是 SQLite 特有的要求)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建数据表基类
Base = declarative_base()

# 依赖注入函数：用于 FastAPI 获取数据库 Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()