# 招投标管理系统

基于 **FastAPI + SQLAlchemy + SQLite** 后端与 **Vue 3（本地运行时，离线可用）** 前端的企业招投标管理系统。

## 功能模块

- **招标项目管理**：项目建档、预算、类别、状态管理（草稿/已发布/招标中/评标中/已定标/已关闭）
- **标段管理**：多标段、评标方法（综合评分法 / 最低价法）、保证金比例、公示天数、资格要求、状态机流转与轨迹记录
- **投标管理**：投标文件提交、报价、证照有效期、技术方案，自动合规校验（必填/日期/范围规则）
- **评标引擎**：
  - 综合评分法：价格分（最低价基准）+ 技术/商务主观分（评委打分、加权）
  - 最低价法：合规通过中最低报价中标，异常低价检测（低于平均价阈值需澄清）
- **中标公示**：公示期管理、到期确认中标
- **保证金账务**：缴纳、退还、没收，完整资金流水
- **审计日志**：全操作留痕

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.10+ / FastAPI / SQLAlchemy 2.0 / SQLite |
| 认证 | JWT（HttpOnly Cookie） |
| 前端 | Vue 3 单页应用（hash 路由，vue.global.js 本地运行时，无需构建工具） |
| 测试 | pytest + httpx |

## 快速开始

```bash
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload
```

访问 http://127.0.0.1:8000 ，登录账号（密码均为 `123456`）：

| 账号 | 角色 | 说明 |
|------|------|------|
| admin | 管理员 | 全部操作权限 |
| operator | 招标经办 | 项目/标段/评标管理 |
| bidder1 / bidder2 / bidder3 | 投标人 | 提交投标、缴纳保证金 |
| judge1 / judge2 / judge3 | 评委 | 评分项打分 |

## 演示数据

初始化脚本预置 2 个项目、3 个标段、3 份已提交的投标文件（标段 BD-2026-001），可直接体验：
发布公告 → 提交投标 → 合规校验 → 缴纳保证金 → 配置评标规则 → 评委打分 → 开标排名 → 公示确认 → 保证金退还。

## 目录结构

```
bid_system/
├── app/
│   ├── main.py            # 应用入口，托管前端静态资源与 API
│   ├── core/              # 配置 / 数据库 / 安全 / 依赖
│   ├── models/            # 16 张数据表
│   ├── schemas/           # Pydantic 校验模型
│   ├── services/          # 业务逻辑（合规校验 / 评标引擎 / 保证金 / 状态机）
│   └── api/               # REST 接口
├── static/
│   ├── index.html         # Vue 单页应用入口
│   ├── css/               # 样式
│   ├── js/                # 路由与视图组件
│   └── vendor/            # Vue 3 本地运行时（离线可用）
├── scripts/init_db.py     # 数据库初始化与演示数据
├── tests/                 # 单元测试
├── data/                  # SQLite 数据库文件
└── requirements.txt
```

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/login | 登录（写 Cookie） |
| GET/POST | /api/projects | 项目列表 / 新建 |
| POST | /api/projects/{id}/sections | 新建标段 |
| GET | /api/sections/{id} | 标段详情（投标/保证金/公示） |
| POST | /api/sections/{id}/transition | 状态流转 |
| POST | /api/sections/{id}/bids | 提交投标（自动合规校验） |
| GET | /api/sections/{id}/evaluation | 评标配置 |
| POST | /api/sections/{id}/evaluation/open | 开标（算分/排名/异常低价/中标候选人） |
| POST | /api/escrow/{id}/return | 退还保证金 |
| GET | /api/dashboard | 统计总览 |
| GET | /api/audit | 审计日志 |

## 测试

```bash
python -m pytest tests/ -v
```
