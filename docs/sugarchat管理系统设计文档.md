# SuggarChat 管理系统设计文档

> 版本：v1.3（2026-08-17）
> 适用范围：SSBot 项目内 nonebot-plugin-suggarchat 3.7.0
> 定位：管理系统（后端 API）先行开发，Web 网页作为派生视图后续开发
> 前置文档：[sugarchat管理与省token设计案.md](./sugarchat管理与省token设计案.md)（治理层设计）
> 依据：NoneBot2 2.5.0 源码核实 + suggarchat config.toml 实际字段 + db.sqlite3 表结构

---

## 0. 结论先行（TL;DR）

- **目标**：把 suggarchat 分散的配置（config.toml）、人格文件（group/private_prompts）、用量数据（db.sqlite3）收敛到一个管理系统，暴露统一 API；网页只是这套 API 的派生视图，不参与核心逻辑。
- **技术底座**：bot 已运行 FastAPI（`DRIVER=~fastapi+~websockets`，8080），NoneBot2 的 `Driver.server_app` 属性可直接 `add_api_route`——**无需另起服务、无需引入新框架**。
- **开发顺序**：P1 只读 API → P2 写操作 API（原子写+备份+热重载）→ P3 网页视图（静态页挂载）。
- **三条红线**：API key 打码只读；db.sqlite3 只读（不绕过 ORM 写库）；所有写操作先备份后原子写。
- **新增配置**：`.env.dev` 增加 `AI_CONFIG_TOKEN`（访问口令，非 QQ 登录）。
- **v1.1 决策**：P1/P2 单独交付；Token 启动时自动生成；备份保留 10 份；用量仅统计次数（详见第 8 章决策记录）。

---

## 1. 系统定位与边界

### 1.1 定位

| 层 | 名称 | 职责 | 归属 |
|---|---|---|---|
| L3 | Web 网页 | 配置表单、人格编辑器、用量图表 | **P3 阶段**，纯静态页 |
| L2 | 管理系统（本设计） | API：读配置/写配置/人格 CRUD/用量查询/备份 | **P1~P2 阶段** |
| L1 | suggarchat 插件 | 实际对话逻辑、热重载 | 第三方，不改源码 |

### 1.2 边界原则

| 事项 | 处理 | 原因 |
|---|---|---|
| config.toml | 管理系统**读写**，原子写 + 备份 | UniConfig 目录监控自动热重载 |
| group/private_prompts | 管理系统**读写**（txt 文件） | 插件目录监控自动重载，零冲突 |
| db.sqlite3 | 管理系统**只读** | 绕过 ORM 写库有锁风险，用量只需展示 |
| suggarchat 源码 | **永不修改** | 升级会被覆盖（见设计案 4.3） |

### 1.3 鉴权模型

- 访问口令 `AI_CONFIG_TOKEN`：**管理系统启动时自动生成随机串并打印到控制台**，无需人工配置（决策 2）
- 浏览器访问 /ai-config/ 输入一次口令，存 localStorage，后续请求带 `X-AI-Config-Token` 头
- 非 Token 登录（不做 QQ OAuth）——本系统仅管理员单机使用，Token 足够

### 1.4 与设计案的配合关系（开发时两个文档共同指导）

| 维度 | 设计案（治理层） | 管理系统设计文档（实现层） | 配合方式 |
|---|---|---|---|
| 职责 | 回答"**为什么/管什么**"：省 Token 策略、管理体系、安全红线、度量指标 | 回答"**怎么实现**"：API 契约、模块结构、原子写、鉴权 | 设计案定策略 → 管理系统按策略实现 |
| 配置项 | 第 2 章 A1~A7 建议值（enable_report、memory_lenth_limit 等） | 第 4 章 9 组配置表单 + 4.4 分组响应 | 管理系统的配置页字段 = 设计案建议值的落地载体 |
| 人格管理 | 3.2 命名规范、≤200 字约束、上线检查 | 4.2 人格 CRUD + name 白名单 | 管理台保存人格时按设计案约束校验（≤200 字提示） |
| 用量限额 | 3.3 预算闭环四层 + usage_limit 建议值 | 4.3 /usage 只读查询 | 管理系统展示用量、承载限额配置 |
| 安全治理 | 3.4 熔断日志、误杀申诉、3.5 度量指标 | 5.3 安全红线（打码/只读/备份） | 管理系统的红线实现设计案的治理要求 |
| 改造纪律 | 4.3 不改源码、patch 清单、可回退 | 1.2 边界原则"永不修改源码" | 两文档同源同要求 |

**使用顺序（开发时）**：先查设计案第 2~3 章确定"要配置什么、阈值多少"→ 再查本文档第 4~5 章确定"API 怎么暴露、实现怎么落地"。冲突时以设计案治理原则为准，实现细节以本文档为准，新增决策登记到第 8 章决策记录。

---

## 2. 技术底座核实（源码级）

### 2.1 FastAPI 挂载

```python
# nonebot.drivers.fastapi.Driver 源码核实：
# - self._server_app = FastAPI(...)     → 实例存在
# - def server_app(self) -> FastAPI     → 属性返回 FastAPI 实例
# - add_api_route / add_api_websocket_route 可用
from nonebot import get_driver
app = get_driver().server_app   # FastAPI 实例，可直接注册路由
```

### 2.2 config.toml 配置组（9 组，全部字段）

| 配置组 | 关键字段 | 管理台分组 |
|---|---|---|
| 顶层 | enable、parse_segments、preset、group_prompt_character、private_prompt_character | 基础设置 |
| `[admin]` | admins、admin_group、allow_send_to_admin | 权限 |
| `[default_preset]` | model、base_url、api_key、protocol | 模型（api_key 打码） |
| `[session]` | session_control、session_control_time、session_control_history、session_max_tokens | 会话 |
| `[autoreply]` | enable、global_enable、probability、keywords | 自动回复 |
| `[function]` | chat_pending_mode、synthesize_forward_message、poke_reply、enable_group_chat、enable_private_chat、allow_custom_prompt | 功能开关 |
| `[llm_config]` | stream、memory_lenth_limit、max_tokens、enable_memory_abstract、block_msg、llm_timeout | 模型参数 |
| `[llm_config.tools]` | enable_tools、enable_report、report_exclude_system_prompt、report_exclude_context、agent_mode_enable | 工具与安全 |
| `[usage_limit]` | enable_usage_limit、group_daily_limit、user_daily_limit、group_daily_token_limit、user_daily_token_limit、total_daily_limit、total_daily_token_limit | 用量限额 |

### 2.3 数据源

| 数据 | 位置 | 读/写 | 说明 |
|---|---|---|---|
| 配置 | `AppData\Roaming\nonebot2\nonebot_plugin_suggarchat\config.toml` | 读写 | TOML 格式，UTF-8 |
| 人格（群） | 同目录 `group_prompts/*.txt` | 读写 | 纯文本，每文件一个人格 |
| 人格（私） | 同目录 `private_prompts/*.txt` | 读写 | 同上 |
| 用量/记忆 | `SSBot\data\nonebot_plugin_orm\db.sqlite3` | 只读 | 表：suggarchat_memory_data、suggarchat_group_config |

---

## 3. 系统架构

```
浏览器 ──http://127.0.0.1:8080/ai-config/──▶ NoneBot2 进程（FastAPI）
                                                  │
                              ┌───────────────────┴───────────────────┐
                              │  管理系统插件 src/plugins/ai_config_console/  │
                              │  _auth.py   Token 鉴权（依赖注入）          │
                              │  _api.py    路由注册（/ai-config/api/*）     │
                              │  _config_store.py  config.toml 读写+备份     │
                              │  _prompt_store.py  人格文件 CRUD             │
                              │  _usage.py        db.sqlite3 只读查询         │
                              │  _models.py       请求/响应 Pydantic 模型      │
                              └──┬───────────┬───────────┬───────────┘
                                 │           │           │
                        config.toml   人格目录txt    db.sqlite3(ro)
```

### 3.1 插件包结构

```
src/plugins/ai_config_console/
├─ __init__.py          # 插件入口：注册路由、读 AI_CONFIG_TOKEN
├─ _auth.py             # Token 鉴权 FastAPI 依赖
├─ _api.py              # 全部 API 路由定义
├─ _config_store.py     # config.toml：读、校验、原子写、备份
├─ _prompt_store.py     # 人格文件：列表、读、写、删（场景隔离）
├─ _usage.py            # db.sqlite3 只读查询（只读模式连接）
├─ _models.py           # Pydantic 请求/响应模型
└─ static/              # P3 阶段：网页静态文件（index.html 等）
```

---

## 4. API 契约（v1）

统一前缀 `/ai-config/api`，全部返回 JSON。鉴权头：`X-AI-Config-Token: <token>`。

### 4.1 状态与配置

| 方法 | 路径 | 说明 | 请求体 | 响应体 |
|---|---|---|---|---|
| GET | `/status` | 系统状态 | - | `{running, suggarchat_loaded, version}` |
| GET | `/config` | 全量配置（api_key 打码） | - | 见 4.4 配置分组 |
| PUT | `/config` | 保存配置（原子写+备份） | 配置分组 JSON | `{ok, backup_path}` |

### 4.2 人格文件

| 方法 | 路径 | 说明 | 请求体 | 响应体 |
|---|---|---|---|---|
| GET | `/prompts/{scene}` | 人格列表（scene=group/private） | - | `{scene, prompts: [{name, size, updated}]}` |
| GET | `/prompts/{scene}/{name}` | 单个人格内容 | - | `{name, content}` |
| PUT | `/prompts/{scene}/{name}` | 新建/覆盖人格 | `{content}` | `{ok}` |
| DELETE | `/prompts/{scene}/{name}` | 删除人格 | - | `{ok}` |

约束：name 仅允许 `[\w\u4e00-\u9fa5_-]{1,50}`；content ≤ 2000 字（管理台校验，设计案要求人格 ≤200 字建议值由网页提示）。

### 4.3 用量与备份

| 方法 | 路径 | 说明 | 请求体 | 响应体 |
|---|---|---|---|---|
| GET | `/usage?days=7` | 用量统计（近 N 天，仅统计次数） | - | `{daily: [{date, count}], groups: [...]}` |
| POST | `/backup` | 手动备份 config+人格 | - | `{ok, backup_path}` |

### 4.4 配置分组响应示例（GET /config）

```json
{
  "basic": {"enable": true, "preset": "default", "group_prompt_character": "default"},
  "admin": {"admins": [], "admin_group": 0},
  "model": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com", "api_key": "sk-****a8bf"},
  "session": {"session_control": false, "session_max_tokens": 5000},
  "autoreply": {"enable": false, "keywords": ["at"]},
  "function": {"synthesize_forward_message": true, "poke_reply": true},
  "llm": {"memory_lenth_limit": 50, "max_tokens": 500, "stream": false},
  "tools": {"enable_report": true, "agent_mode_enable": false},
  "usage_limit": {"enable_usage_limit": false, "group_daily_limit": 100}
}
```

---

## 5. 关键实现点

### 5.1 config.toml 原子写 + 备份（写操作核心）

```
PUT /config 流程：
1. 校验：请求 JSON 按 _models 校验（字段类型、取值范围、key 规则）
2. 备份：复制 config.toml → data/backups/config_YYYYMMDD_HHMMSS.toml（保留最近 10 份）
3. 原子写：写 config.toml.tmp → os.replace() 覆盖（避免写一半被 UniConfig 读到）
4. 热重载：UniConfig 目录监控自动检测变化，无需重启
5. 返回 {ok, backup_path}
```

### 5.2 鉴权（FastAPI 依赖）

```python
# _auth.py 核心逻辑（伪码）
# Token 来源：管理系统启动时 secrets.token_urlsafe(16) 自动生成，print 到控制台
# 运行期内保存在插件内存；重启后重新生成（单机个人使用，可接受）
from fastapi import Header, HTTPException

TOKEN = ""  # 启动时由 __init__.py 注入

def require_token(x_ai_config_token: str = Header(default="")) -> None:
    if not TOKEN or x_ai_config_token != TOKEN:
        raise HTTPException(401, "invalid token")
```

### 5.3 安全红线

| 红线 | 实现 |
|---|---|
| api_key 打码 | GET /config 返回 `sk-****` + 后 4 位；前端只读展示 |
| db 只读 | `sqlite3.connect("file:...?mode=ro", uri=True)` 只读模式 |
| 路径穿越防护 | 人格 name 白名单正则，禁止 `..`、`/`、`\` |
| 写前备份 | 所有写操作（配置/人格删除）先备份，保留最近 10 份（决策 3） |
| Token 来源 | 启动时自动生成并打印控制台（决策 2）；未生成时拒绝访问（fail-safe） |

---

## 6. 网页派生方案（P3，已完成 2026-08-17）

- 静态页放 `static/`，FastAPI 挂载：`app.mount("/ai-config", StaticFiles(directory=static, html=True))`；static 目录存在才挂载（不存在仅警告不报错）
- 页面结构（单页应用，原生 JS，无构建，零依赖）：
  - **登录页**：Token 输入 → localStorage，401 自动登出
  - **配置页**：9 组配置表单（分组折叠），字段级元数据（label/说明/示例），布尔→开关、数组→逗号分隔、长文本→textarea；只读字段禁用 + api_key 打码；可写/只读徽标
  - **人格页**：group/private 双 Tab，列表 + 编辑器 + 新建/删除
  - **用量页**：SVG 柱状图（原生绘制），近 7/14/30 天切换，次数 + Token 双图
  - **备份页**：手动备份 config.toml，展示备份文件名
- **API 契约即前后端接口**：网页只调 4.1~4.3 的 API，不接触文件系统
- **实现文件**：`src/plugins/ai_config_console/static/index.html`；测试 `scripts/test_ai_config_web.py`（17/17 通过）

---

## 7. 开发里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1 只读 API | 插件骨架、_auth、_api GET 路由、_usage、_models | ✅ 已完成（curl 验证通过） |
| P2 写操作 API | _config_store 原子写+备份、_prompt_store CRUD | ✅ 已完成（30/30 测试通过） |
| P3 网页 | static/ 单页：登录/配置/人格/用量/备份 | ✅ 已完成（17/17 测试通过） |
| P4 收尾 | README 补充、变更记录、备份清理策略 | ✅ 已完成（README 含配置台章节） |

> 交付节奏决策（决策 1）：P1/P2 先交付（curl 可验），P3 网页随后开发，现已全部完成。

---

## 8. 决策记录（2026-08-17 已确认）

| # | 决策项 | 结论 | 影响 |
|---|---|---|---|
| 1 | 交付节奏 | **P1/P2 单独交付**（后端 API，curl 可验），P3 网页验收后再排期 | 里程碑按此调整（见第 7 章） |
| 2 | AI_CONFIG_TOKEN | **启动时自动生成随机串并打印到控制台**，无需人工配置 | 鉴权模型与 _auth 实现按此设计（见 1.3、5.2） |
| 3 | 备份保留 | config 备份**保留最近 10 份**，暂不加清理按钮 | 安全红线按此固化（见 5.3） |
| 4 | 用量统计口径 | **仅统计次数可接受**；若 memory_data 表字段足以聚合 token 则顺带提供，字段不足不阻塞 | /usage 响应按次数设计（见 4.3） |
| 5 | admin 组纳入网页 | **`[admin]` 组（admins/admin_group/allow_send_to_admin）网页可编辑**——管理系统网页仅内部开发人员可登录（Token 门禁），无需隔离权限管理；**SUPERUSERS 维持 .env 单一来源，不进网页** | EDITABLE_MAP 增加 admin 组；配置项清单 v1.1 |

> 决策 4 附注：开发 P1 时实际查询 db.sqlite3 表结构，若 `suggarchat_memory_data` 含时间戳字段则按日统计次数；若含 token 计数字段则顺带输出 tokens，不额外设计。
> 决策 5 附注：admins 为 QQ 号列表，前端标签输入；网页可编辑 admin 组不影响 SUPERUSERS（.env）对 NoneBot 全局的管控。

---

## 附录：变更记录

| 日期 | 变更内容 | 修改人 |
|---|---|---|
| 2026-08-17 | 初版设计文档（v1.0） | 王遵诗 / WorkBuddy |
| 2026-08-17 | v1.1：4 项决策定稿（P1/P2 单独交付、Token 自动生成、备份保留 10 份、用量仅统计次数），第 8 章改为决策记录，同步更新 1.3/4.3/5.2/5.3/7 章 | 王遵诗 / WorkBuddy |
| 2026-08-17 | v1.2：新增决策 5——admin 组纳入网页可编辑（admins/admin_group/allow_send_to_admin），SUPERUSERS 维持 .env 单一来源 | 王遵诗 / WorkBuddy |
| 2026-08-17 | v1.3：P3 网页完成——第 6 章改为实现说明（5 视图 + 字段元数据 + 测试 17/17），第 7 章里程碑全部 ✅ | 王遵诗 / WorkBuddy |
