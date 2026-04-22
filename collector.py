"""
铂钯实时行情数据采集器
独立进程运行，定时写入数据库
"""

import os
import sys
import logging
import datetime
import asyncio
import signal
from collections import deque

from tqsdk import TqApi, TqAuth, TqKq
import sqlalchemy as db
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, String, Float, Integer, DateTime, UniqueConstraint, create_engine
from sqlalchemy.ext.declarative import declarative_base

# ---------------------------- 日志配置 ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("collector")

# ---------------------------- 数据库配置 ----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("未找到 DATABASE_URL 环境变量")
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
        logger.warning(f"建表时出错: {e}")


# ---------------------------- 天勤配置 ----------------------------
TQ_ACCOUNT = os.getenv("TQ_ACCOUNT")
TQ_PASSWORD = os.getenv("TQ_PASSWORD")

if not TQ_ACCOUNT or not TQ_PASSWORD:
    logger.error("请设置 TQ_ACCOUNT 和 TQ_PASSWORD 环境变量")
    sys.exit(1)

# 合约列表（根据实际调整）
# 使用具体合约，避免主连换月问题
SYMBOLS = os.getenv("SYMBOLS", "KQ.m@GFEX.pt,KQ.m@GFEX.pd").split(",")


# ---------------------------- 数据处理 ----------------------------

def get_tick_values(quote) -> dict | None:
    """提取 tick 字段"""
    try:
        dt_str = quote.datetime
        if not dt_str or str(dt_str).strip() == "":
            return None
        dt = datetime.datetime.strptime(str(dt_str)[:23], "%Y-%m-%d %H:%M:%S.%f")
    except Exception:
        dt = datetime.datetime.now()

    try:
        return {
            "last_price": float(quote.last_price) if quote.last_price else None,
            "volume": int(quote.volume) if quote.volume else None,
            "bid_price1": float(quote.bid_price1) if quote.bid_price1 else None,
            "ask_price1": float(quote.ask_price1) if quote.ask_price1 else None,
            "bid_volume1": int(quote.bid_volume1) if quote.bid_volume1 else None,
            "ask_volume1": int(quote.ask_volume1) if quote.ask_volume1 else None,
            "datetime": dt,
        }
    except Exception:
        return None


# ---------------------------- 批次写入 ----------------------------

class TickWriter:
    """缓冲写入，减少 IO"""

    def __init__(self, batch_size: int = 50, flush_interval: float = 5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffer: deque = deque()
        self.last_flush = datetime.datetime.now()

    def add(self, symbol: str, values: dict):
        self.buffer.append((symbol, values))
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        session = SessionLocal()
        count = 0
        try:
            while self.buffer:
                symbol, values = self.buffer.popleft()
                try:
                    tick = TickData(symbol=symbol, **values)
                    session.add(tick)
                    count += 1
                except Exception:
                    pass
            session.commit()
            if count > 0:
                logger.info(f"批次写入 {count} 条")
        except Exception as e:
            session.rollback()
            logger.error(f"批次写入失败: {e}")
        finally:
            session.close()

    def auto_flush(self):
        if (datetime.datetime.now() - self.last_flush).total_seconds() >= self.flush_interval:
            self.flush()
            self.last_flush = datetime.datetime.now()


# ---------------------------- 主程序 ----------------------------

class Collector:
    def __init__(self):
        self.api = None
        self.running = False
        self.quotes = {}
        self.last_data_time = {}
        self._shutdown_requested = False

    def _request_shutdown(self, signum=None, frame=None):
        """信号处理：标记关闭，不在信号处理函数中做清理"""
        logger.info(f"收到停止信号，准备优雅退出...")
        self._shutdown_requested = True
        self.running = False

    def _graceful_close(self):
        """确保 TqApi 正确关闭，清理 asyncio 事件循环"""
        if self.api is not None:
            try:
                self.api.close()
                logger.info("TqApi 已关闭")
            except Exception as e:
                logger.warning(f"TqApi 关闭时出错: {e}")
            finally:
                self.api = None

        # 清理残留的 asyncio 任务和事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                # 取消所有未完成的任务
                pending = asyncio.all_tasks(loop) if hasattr(asyncio, 'all_tasks') else asyncio.Task.all_tasks(loop)
                for task in pending:
                    task.cancel()
                # 等待任务取消完成
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()
                logger.info("asyncio 事件循环已清理")
        except RuntimeError:
            # 没有 event loop，忽略
            pass
        except Exception as e:
            logger.debug(f"清理事件循环时出错（可忽略）: {e}")

    def start(self):
        init_db()

        # 注册信号处理
        signal.signal(signal.SIGTERM, self._request_shutdown)
        signal.signal(signal.SIGINT, self._request_shutdown)

        logger.info("连接天勤...")
        try:
            self.api = TqApi(TqKq(), auth=TqAuth(TQ_ACCOUNT, TQ_PASSWORD), debug=False)
            logger.info("天勤连接成功")
        except Exception as e:
            logger.error(f"天勤连接失败: {e}")
            sys.exit(1)

        # 订阅合约
        for sym in SYMBOLS:
            try:
                q = self.api.get_quote(sym)
                self.quotes[sym] = q
                logger.info(f"已订阅: {sym}")
            except Exception as e:
                logger.warning(f"订阅 {sym} 失败: {e}")

        if not self.quotes:
            logger.error("没有合约订阅成功")
            self._graceful_close()
            sys.exit(1)

        writer = TickWriter(batch_size=50, flush_interval=5.0)
        self.running = True

        logger.info("开始采集...")
        try:
            while self.running:
                try:
                    self.api.wait_update(deadline=30)
                except Exception as e:
                    if self._shutdown_requested:
                        break
                    logger.warning(f"wait_update 异常: {e}")
                    continue

                for sym, quote in self.quotes.items():
                    try:
                        current_dt = str(quote.datetime)
                        key = f"{sym}_dt"
                        if current_dt != self.last_data_time.get(key):
                            self.last_data_time[key] = current_dt
                            values = get_tick_values(quote)
                            if values and values["last_price"] is not None:
                                writer.add(sym, values)
                    except Exception as e:
                        logger.debug(f"{sym} 解析出错: {e}")

                writer.auto_flush()

                # 检查关闭信号
                if self._shutdown_requested:
                    break

        except Exception as e:
            logger.error(f"运行错误: {e}", exc_info=True)
        finally:
            writer.flush()
            self._graceful_close()
            logger.info("采集器已停止")


if __name__ == "__main__":
    Collector().start()
