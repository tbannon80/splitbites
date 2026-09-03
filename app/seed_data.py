import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from app.database import Base

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://secondbrain:secondbrainpass@localhost:5432/secondbrain')

async def init_db():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('Database tables created successfully.')
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(init_db())
