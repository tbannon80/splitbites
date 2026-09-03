from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import meal_plans

app = FastAPI(title="SplitBites API", version="1.0.0")

# CORS middleware for local frontend and network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.4.35:3000",
        "http://192.168.4.35:5173",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meal_plans.router)

@app.get("/healthz")
async def health_check():
    return {"status": "healthy", "service": "splitbites-backend"}
