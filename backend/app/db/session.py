from app.core.config import settings

from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import(
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)

#管理数据库的连接
engine:AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

#创建会话的工厂方法
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind = engine,
    expire_on_commit = False,
    autoflush=False,
)

#获取session,用yield每次生产一个session
async def get_session() ->AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session