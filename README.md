# SSBot

基于 [NoneBot2](https://nonebot.dev/) + OneBot V11 适配器的 QQ 群聊机器人，协议端使用 [NapCat](https://napcat.napneko.icu/)。

## 功能特性

| 功能 | 说明 | 入口 |
|---|---|---|
| AI 群聊 | 集成 SuggarChat，支持 DeepSeek 对话、记忆、人设切换 | @机器人 |
| **AI 配置台** | 网页管理系统：配置/人格/用量管理 API（内置注入防护与权限守卫） | `http://127.0.0.1:8080/ai-config/` |
| 影之诗查卡 | 735 张中文卡牌模糊搜索 / 职业过滤 / 精确 ID 查询 | `/sv` |
| JM 漫画下载 | JM 漫画搜索、选择、下载、PDF 生成 | `/jm`、`/jm_search` |
| 交互式帮助菜单 | 分类展示全部命令；默认纯文本（第三方协议端不渲染 json 卡片） | `/help` |
| 群信息与娱乐 | 当前群信息摘要、随机情话、井字棋人机对弈 | `/get_list`、`/whoami`、`/情话`、`/井字棋` |
| 跑团（CoC） | AI 主持人 P1：车卡、开团、行动结算、场景/线索、检定（独立 SQLite + 模板/LLM 叙事） | `/coc` |

## 技术栈

- **Python**: 3.9+（开发环境 3.12）
- **机器人框架**: NoneBot2 2.5.0
- **适配器**: OneBot V11 2.4.6（反向 WebSocket 连接 NapCat）
- **AI**: DeepSeek API（通过 nonebot-plugin-suggarchat 接入）
- **数据库**: SQLite + aiosqlite（存储 SuggarChat 对话记忆与用量）
- **AI 配置台**: 复用 bot 的 FastAPI（`/ai-config/api/*`），Token 鉴权，配置/人格/用量管理

## 快速开始

### 1. 环境要求

- Python 3.9+
- [NapCat](https://napcat.napneko.icu/) 已启动，WebSocket 客户端指向 `127.0.0.1:8080/onebot/v11/ws`

### 2. 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活（Windows）
.venv\Scripts\activate

# 安装依赖（含全部插件与 AI 聊天）
pip install -e .
```

### 3. 配置

复制 `.env.example` 为 `.env.dev`（或设置 `ENVIRONMENT` 环境变量选择 `.env.{环境名}`），填入配置：

| 配置项 | 说明 |
|---|---|
| `HOST` / `PORT` | Bot 监听地址与端口（默认 127.0.0.1:8080），需与 NapCat 反代 WebSocket 一致 |
| `ONEBOT_WS_PATH` | OneBot V11 WebSocket 路径（默认 `/onebot/v11/ws`） |
| `SUPERUSERS` | 超级管理员 QQ 号（JSON 数组格式 `["123456"]`），suggarchat 权限单一来源 |
| `DEEPSEEK_API_KEY` | 必填，AI 聊天用，从 [DeepSeek 平台](https://platform.deepseek.com/api_keys) 获取 |
| `SQLALCHEMY_DATABASE_URL` | SuggarChat 记忆数据库，默认 `sqlite+aiosqlite:///./data/nonebot_plugin_orm/db.sqlite3` |
| `LOG_LEVEL` | 日志级别，日常 `INFO`，排障 `DEBUG` |

> 注：suggarchat 的配置文件位于 `AppData\Roaming\nonebot2\nonebot_plugin_suggarchat\config.toml`，其中 `${DEEPSEEK_API_KEY}` 占位符从环境变量读取。

### 4. 运行

```bash
nb run
```

启动后 NapCat 控制台应显示 `Bot <QQ号> connected`。

## 命令手册

### AI 聊天（SuggarChat）

| 命令 | 说明 |
|---|---|
| @机器人 + 消息 | 触发 AI 对话（也可在 `config.toml` 改 keywords 配置） |
| `/choose_prompt group/private [名字]` | 查看/切换群聊/私聊人格（仅 bot 管理员） |
| `/prompt --(show/--set/--clear)` | 查看/设置/清空自定义 prompt（群聊需群管，私聊仅管理员） |
| `/insights` | 查看 Token 用量与统计 |
| `/del_memory` | 清空当前会话记忆（切换人格后建议执行） |
| `/test_preset` | 验证当前预设配置 |

**人格文件**（`AppData\Roaming\nonebot2\nonebot_plugin_suggarchat\group_prompts\` 与 `private_prompts\`）：
- `私聊_默认.txt` / `群聊_默认.txt`：内置场景人格（含反注入声明与"不输出内心独白"约束）
- 人格文件与 `/prompt` 是两套独立存储：人格文件走 SYSTEM_INSTRUCTIONS，`/prompt` 走 EXTRA（存数据库）

**已内置防护**：
- 提示词注入拦截（D2 钩子）：聊天中"你是猫娘/【PERSONA_LOAD】"等注入话术会被中和
- 私聊 `/prompt` 权限守卫：非管理员无法在私聊设置人格

完整用法见 [docs/sugarchat使用指南.md](docs/sugarchat使用指南.md)。

### AI 配置台（管理系统）

启动 bot 后控制台打印访问口令，浏览器打开 `http://127.0.0.1:8080/ai-config/`：

| 能力 | 说明 |
|---|---|
| 配置管理 | 读写 suggarchat 全部配置组（模型/会话/自动回复/功能/限额/权限），每个字段带说明与示例，api_key 打码 |
| 人格管理 | 群聊/私聊人格文件列表、查看、编辑、新建、删除 |
| 用量统计 | 近 7/14/30 天 Token 与调用次数图表（只读 db） |
| 备份 | 手动备份 config.toml（保留 10 份） |

> 单页应用（原生 JS 无构建），已全部完成；设计见 [docs/sugarchat管理系统设计文档.md](docs/sugarchat管理系统设计文档.md)。

### 影之诗查卡

| 命令 | 说明 |
|---|---|
| `/sv <关键词>` | 模糊搜索卡牌 |
| `/sv #<职业>` | 按职业过滤（中立/精灵/皇家/法师/龙族/梦魇/主教/超越者） |
| `/sv !<ID>` | 按 8 位 card_id 精确查询 |
| `/sv_reload` | 重载卡牌数据 |

> 单卡/ID 查询会附卡牌图片（shadowverse-portal 直链）；列表结果回复 `/sv !<ID>` 可看单卡大图。

### 跑团（CoC 7e）

| 命令 | 说明 |
|---|---|
| `/coc 开团 [模组]` | 开局（管理员）：加载内置模组并进入首个场景 |
| `/coc 车卡 [名字]` | 随机生成调查员 |
| `/coc 行动 <做什么>` | 在当前场景行动（调查/交谈/移动/使用物品），自动掷检定 |
| `/coc 场景` | 当前场景、回合、张力与出口 |
| `/coc 线索` | 已发现线索 |
| `/coc 检定 <技能> [困难/极难]` | 单独掷一次技能检定 |
| `/coc 状态` | 角色卡与派生值 |
| `/coc 结束` | 结束本局（管理员） |

> 叙事默认用确定性模板（离线可跑）；设 `COC_LLM_ENABLED=true` + `DEEPSEEK_API_KEY` 可切换 LLM 叙事，失败自动回退模板。
> 内置示例模组：`src/plugins/coc_keeper/data/modules/wugang.json`（3 场景 / 5 线索 / 2 NPC / 2 结局）。

### 其他插件

| 命令 | 说明 |
|---|---|
| `/help [分类]` | 查看帮助菜单（纯文本，可配 `HELP_USE_CARD=true` 改用 json 卡片）；`/help_reload` 热重载菜单配置 |
| `/jm <漫画号>` | 下载指定 JM 漫画 |
| `/jm_search <关键词>` | 搜索 JM 漫画并交互选择 |
| `/get_list` | 查看当前群信息与成员概览（@机器人） |
| `/whoami` | 查看自己的昵称与 QQ（@机器人） |
| `/情话` | 随机一句情话，接口不可用自动兜底（@机器人） |
| `/井字棋` | 人机对弈：`/井字棋` 开局，回 1-9 落子，`/井字棋 结束` 退出（@机器人） |

## 项目结构

```
SSBot/
├─ bot.py                 # 入口：env 加载、适配器注册、插件加载
├─ pyproject.toml         # 依赖与 NoneBot 配置
├─ .env.example           # 配置模板（复制为 .env.dev）
├─ src/plugins/           # 全部插件
│  ├─ ai_config_console/  # AI 配置台（API + 注入防护 + 权限守卫）
│  ├─ interactive_help/   # 帮助菜单
│  ├─ sv_card/            # 影之诗查卡
│  ├─ jm_downloader/      # JM 漫画下载
│  ├─ get_group_info/     # 群信息
│  ├─ plugin_nonebot_rand_qinghua/  # 随机情话
│  ├─ tic_tac_toe/        # 井字棋（人机对弈）
│  └─ coc_keeper/         # 跑团（CoC 7e）：domain/store/runtime/module
├─ scripts/               # 工具脚本（API / 网页 / 回归 / 冒烟测试）
├─ docs/                  # 使用与设计文档
└─ data/                  # 运行时数据（SQLite 记忆库、配置备份）
```

## 文档

- [SuggarChat 使用指南](docs/sugarchat使用指南.md)
- [SuggarChat 管理与省 Token 设计案](docs/sugarchat管理与省token设计案.md)（治理层 + 已知问题防护）
- [SuggarChat 管理系统设计文档](docs/sugarchat管理系统设计文档.md)（实现层：API 契约）
- [SuggarChat 网页配置项清单](docs/sugarchat网页配置项清单.md)（字段层：网页表单对照）
- [缺陷修复记录](docs/缺陷修复记录.md)（D-01~D-14：现象 / 根因 / 修复 / 验证）
- [AI 跑团主持人（CoC KP）设计分析](docs/CoC跑团KP设计分析.md)（设计阶段，未实现：架构 / 规则 / 剧本 / 回合 / 复盘）

## License

本项目仅用于个人学习与娱乐用途。
