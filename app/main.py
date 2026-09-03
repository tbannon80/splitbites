from fastapi import FastAPI
from app.routers import meal_plans

app = FastAPI(title="SplitBites API", version="1.0.0")

app.include_router(meal_plans.router)

@app.get("/healthz")
async def health_check():
    return {"status": "healthy", "service": "splitbites-backend"}
