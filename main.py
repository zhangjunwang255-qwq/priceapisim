"""
铂钯实时行情 API 服务
部署：Railway + Railway PostgreSQL + TqKq
"""

import os
import sys
import logging
import datetime
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlalchemy as db
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, String, Float, Integer, DateTime, UniqueConstraint, create_engine, desc, func
from sqlalchemy.ext.declarative import declarative_base

# ---------------------------- 日志配置 ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("price_api")

# ---------------------------- 数据库配置 ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("未找到 DATABASE_URL 环境变量，请确认 Railway 数据库已绑定")
    sys.exit(1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=1)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class TickData(Base):
    __tablename__ = "tick_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    datetime = Column(DateTime, nullable=False)
    last_price = Column(Float)
    volume = Column(Integer)
    bid_price1 = Column(Float)
    ask_price1 = Column(Float)
    bid_volume1 = Column(Integer)
    ask_volume1 = Column(Integer)

    __table_args__ = (
        UniqueConstraint("symbol", "datetime", name="uq_symbol_datetime"),
    )


def init_db():
    try:
        Base.metadata.create_all(engine)
        logger.info("数据库表已就绪")
    except Exception as e:
        logger.warning(f"建表时出错（可能已存在）: {e}")


# ---------------------------- FastAPI 应用 ----------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    init_db()
    yield
    # 关闭时清理资源
    pass


app = FastAPI(
    title="Price API Sim",
    description="铂钯实时行情 API（模拟账户版）",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------- 数据模型 ----------------------------

class TickResponse(BaseModel):
    symbol: str
    datetime: str
    last_price: Optional[float]
    volume: Optional[int]
    bid_price1: Optional[float]
    ask_price1: Optional[float]
    bid_volume1: Optional[int]
    ask_volume1: Optional[int]

    class Config:
        from_attributes = True


class LatestResponse(BaseModel):
    symbol: str
    last_price: Optional[float]
    bid_price1: Optional[float]
    ask_price1: Optional[float]
    volume: Optional[int]
    datetime: str


# ---------------------------- API 路由 ----------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    """前端页面"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>铂钯实时行情</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; font-weight: 300; letter-spacing: 2px; }
        .card { 
            background: rgba(255,255,255,0.1); 
            border-radius: 16px; 
            padding: 24px;
            margin-bottom: 16px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card-header { 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
            margin-bottom: 16px;
        }
        .symbol { font-size: 24px; font-weight: 600; }
        .symbol.pb { color: #e6c200; }
        .symbol.pd { color: #c0c0c0; }
        .price { font-size: 36px; font-weight: 700; }
        .price.up { color: #00d4aa; }
        .price.down { color: #ff6b6b; }
        .info { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 14px; color: rgba(255,255,255,0.7); }
        .info-item { display: flex; justify-content: space-between; }
        .loading { text-align: center; padding: 40px; color: rgba(255,255,255,0.5); }
        .error { text-align: center; padding: 40px; color: #ff6b6b; }
        .refresh { 
            text-align: center; 
            margin-top: 20px;
            color: rgba(255,255,255,0.5);
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🥈 铂钯实时行情</h1>
        <div id="app">Loading...</div>
        <div class="refresh">自动刷新每 3 秒</div>
    </div>
    <script>
        const colors = { pb: '#e6c200', pd: '#c0c0c0' };
        
        async function fetchData() {
            try {
                const resp = await fetch('/api/latest');
                const data = await resp.json();
                render(data);
            } catch(e) {
                document.getElementById('app').innerHTML = '<div class="error">加载失败: ' + e.message + '</div>';
            }
        }
        
        function render(data) {
            if (!data || data.length === 0) {
                document.getElementById('app').innerHTML = '<div class="loading">暂无数据</div>';
                return;
            }
            
            let html = '';
            data.forEach(item => {
                const symbolClass = item.symbol.toLowerCase().includes('pb') ? 'pb' : 'pd';
                const color = colors[symbolClass] || '#fff';
                html += `
                    <div class="card">
                        <div class="card-header">
                            <span class="symbol ${symbolClass}">${item.symbol}</span>
                            <span style="color: rgba(255,255,255,0.5); font-size: 12px;">${item.datetime}</span>
                        </div>
                        <div class="price" style="color: ${color}">${item.last_price?.toFixed(2) || '--'}</div>
                        <div class="info">
                            <div class="info-item"><span>买价</span><span>${item.bid_price1?.toFixed(2) || '--'}</span></div>
                            <div class="info-item"><span>卖价</span><span>${item.ask_price1?.toFixed(2) || '--'}</span></div>
                            <div class="info-item"><span>买量</span><span>${item.bid_volume1 ?? '--'}</span></div>
                            <div class="info-item"><span>卖量</span><span>${item.ask_volume1 ?? '--'}</span></div>
                            <div class="info-item"><span>成交量</span><span>${item.volume ?? '--'}</span></div>
                        </div>
                    </div>
                `;
            });
            document.getElementById('app').innerHTML = html;
        }
        
        fetchData();
        setInterval(fetchData, 3000);
    </script>
</body>
</html>"""


@app.get("/api/latest", response_model=list[LatestResponse])
async def get_latest(symbols: str = Query("", description="合约代码逗号分隔，如 GFEX.pb2406,GFEX.pd2406")):
    """获取各合约最新行情"""
    session = SessionLocal()
    try:
        result = []
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else ["GFEX.pb2406", "GFEX.pd2406"]
        
        for sym in symbol_list:
            # 查询每个合约的最新一条
            tick = session.query(TickData).filter(
                TickData.symbol == sym
            ).order_by(desc(TickData.datetime)).first()
            
            if tick:
                result.append(LatestResponse(
                    symbol=tick.symbol,
                    last_price=tick.last_price,
                    bid_price1=tick.bid_price1,
                    ask_price1=tick.ask_price1,
                    volume=tick.volume,
                    datetime=tick.datetime.strftime("%Y-%m-%d %H:%M:%S") if tick.datetime else ""
                ))
        
        return result
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/api/history", response_model=list[TickResponse])
async def get_history(
    symbol: str = Query(..., description="合约代码"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数")
):
    """获取历史行情"""
    session = SessionLocal()
    try:
        ticks = session.query(TickData).filter(
            TickData.symbol == symbol
        ).order_by(desc(TickData.datetime)).limit(limit).all()
        
        return [TickResponse(
            symbol=t.datetime.strftime("%Y-%m-%d %H:%M:%S") if t.datetime else "",
            datetime=t.datetime.strftime("%Y-%m-%d %H:%M:%S") if t.datetime else "",
            last_price=t.last_price,
            volume=t.volume,
            bid_price1=t.bid_price1,
            ask_price1=t.ask_price1,
            bid_volume1=t.bid_volume1,
            ask_volume1=t.ask_volume1
        ) for t in ticks]
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# ---------------------------- 健康检查 ----------------------------

@app.get("/health")
async def health():
    """Railway 健康检查"""
    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
