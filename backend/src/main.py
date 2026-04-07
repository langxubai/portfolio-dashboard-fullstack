from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.scheduler import start_scheduler, shutdown_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    shutdown_scheduler()

app = FastAPI(
    title="Personal Finance Dashboard API",
    description="Backend API for managing personal finance accounts, assets, transactions, and alerts.",
    version="1.0.0",
    lifespan=lifespan
)

# 配置 CORS，允许前端（如 Streamlit 或 iOS 小组件）跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 生产环境下建议限制具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Personal Finance Dashboard API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

from src.routers import accounts, assets, transactions, alert_rules, positions, portfolio, market
app.include_router(accounts.router)
app.include_router(assets.router)
app.include_router(transactions.router)
app.include_router(alert_rules.router)
app.include_router(positions.router)
app.include_router(portfolio.router)
app.include_router(market.router)
