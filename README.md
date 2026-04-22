# Price API Sim - 铂钯实时行情 API

基于天勤量化（TqSdk）模拟账户获取广期所铂钯实时行情，部署于 Railway。

## 功能

- **API 服务** (`main.py`): 提供 REST API 查询最新行情和历史数据
- **数据采集器** (`collector.py`): 后台进程采集实时数据写入数据库
- **前端页面**: 简陋的实时行情展示页面

## 快速部署

### 1. 推送到 GitHub

```bash
# 创建仓库后，克隆到本地
git clone https://github.com/<你的用户名>/priceapisim.git
cd priceapisim

# 复制配置
cp .env.example .env
# 编辑 .env 填入你的快期账号密码
```

### 2. Railway 部署

1. 登录 [Railway](https://railway.app)
2. 创建新项目 → Deploy from GitHub repo
3. 添加插件 → PostgreSQL
4. 在 Variables 中添加：
   - `TQ_ACCOUNT` = 你的快期账号
   - `TQ_PASSWORD` = 你的快期密码
   - `SYMBOLS` = GFEX.pb2406,GFEX.pd2406（或实际合约代码）
5. Deploy

### 3. 验证

- 健康检查: `https://<你的域名>/health`
- API: `https://<你的域名>/api/latest`
- 前端: `https://<你的域名>/`

## 本地测试

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
编辑 .env 填入实际值

# 3. 启动采集器（新终端）
source .env
python collector.py

# 4. 启动 API（新终端）
source .env
python main.py
```

## API 接口

| 接口 | 说明 | 参数 |
|------|------|------|
| `GET /` | 前端页面 | - |
| `GET /api/latest` | 最新行情 | `symbols` 逗号分隔，默认 GFEX.pb2406,GFEX.pd2406 |
| `GET /api/history` | 历史数据 | `symbol` 必填，`limit` 默认 100 |
| `GET /health` | 健康检查 | - |

## 合约代码

广期所铂钯合约代码格式：
- 铂金: `GFEX.pb<年份><月份>`，如 `GFEX.pb2406`（2024年6月）
- 钯金: `GFEX.pd<年份><月份>`，如 `GFEX.pd2406`

**注意**: 合约有换月周期，月底/月初需要更新 `SYMBOLS` 环境变量。

## 目录结构

```
priceapisim/
├── main.py          # FastAPI 服务
├── collector.py    # 数据采集器
├── requirements.txt # 依赖
├── Procfile        # Railway 进程定义
├── railway.json    # Railway 配置
├── .env.example   # 环境变量示例
└── README.md
```# priceapisim
