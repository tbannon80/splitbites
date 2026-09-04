import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from app.routers import meal_plans, households, recipes, auth, feedback, pantry

app = FastAPI(title="SplitBites API", version="1.0.0")

# CORS middleware for local frontend, reverse proxy, and network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://splitbites.tbannon80-hp-mini.stream",
        "http://splitbites.tbannon80-hp-mini.stream",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.4.35:8001",
        "http://192.168.4.35:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth.router)
app.include_router(meal_plans.router)
app.include_router(households.router)
app.include_router(recipes.router)
app.include_router(feedback.router)
app.include_router(pantry.router)

@app.get("/healthz")
@app.head("/healthz")
async def health_check():
    return {"status": "healthy", "service": "splitbites-backend"}

@app.get("/", response_class=FileResponse)
@app.head("/", response_class=FileResponse)
@app.get("/dashboard", response_class=FileResponse)
@app.head("/dashboard", response_class=FileResponse)
@app.get("/register", response_class=FileResponse)
@app.head("/register", response_class=FileResponse)
@app.get("/login", response_class=FileResponse)
@app.head("/login", response_class=FileResponse)
async def serve_dashboard():
    index_path = STATIC_DIR / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)
    return HTMLResponse("<h1>SplitBites Backend Active</h1>")
