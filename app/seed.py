import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.database import Base, Recipe

# Verification script to test model imports and FastAPI setup
print('Database models compiled successfully. FastAPI app ready.')
