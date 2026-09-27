import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, bids, dashboard, escrow, evaluation, projects, winner
from app.core.database import Base, engine
import app.models  # noqa: F401  确保所有模型已注册

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="招投标管理系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def ensure_tables():
    Base.metadata.create_all(bind=engine)


for router in (auth.router, projects.router, bids.router, evaluation.router, escrow.router, winner.router, dashboard.router):
    app.include_router(router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str):
    """SPA hash 路由无需服务端 fallback；非静态路径一律回退首页。"""
    full = STATIC_DIR / path
    if path and full.exists() and full.is_file():
        return FileResponse(str(full))
    return FileResponse(str(STATIC_DIR / "index.html"))
