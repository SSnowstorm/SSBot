# JM Downloader 可移植架构与流程文档

## 架构设计：单一真相源路径注入

### 核心原则

所有文件路径由 `config.py` 通过 `Path(__file__)` 计算绝对路径，作为唯一真相源（Single Source of Truth）。YAML 配置文件仅作为功能模板，不含任何路径配置。运行时由 `jm_api.py` 读取 YAML 为 dict，注入绝对路径后构造 `JmOption`。

```
┌─────────────────────────────────────────────────────────────┐
│                      config.py                              │
│  _PLUGIN_DIR = Path(__file__).parent                        │
│  jm_download_path = _PLUGIN_DIR / "data" / "downloads"      │
│  jmcomic_option_file = _PLUGIN_DIR / "data" / "jmcomic_options.yml" │
└──────────────────────┬──────────────────────────────────────┘
                       │ 绝对路径
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              jm_api.py: _load_jmcomic_option()              │
│                                                             │
│  1. 读取 YAML 为 dict（纯功能模板，无路径）                    │
│  2. 注入绝对路径：                                            │
│     - dict['dir_rule']['base_dir'] = download_path          │
│     - dict['plugins']['after_album'][i]['kwargs']['pdf_dir'] = download_path │
│  3. JmOption.construct(dict) → JmOption 实例                 │
└──────────────────────┬──────────────────────────────────────┘
                       │ JmOption（含注入路径）
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    jmcomic.download_album()                  │
│                                                             │
│  下载图片 → 转换为 PNG → 触发 img2pdf 插件                    │
│  → 生成 {comic_id}.pdf → 删除原始图片                         │
│  → 文件落在 src/plugins/jm_downloader/data/downloads/       │
└─────────────────────────────────────────────────────────────┘
```

### 路径解析示例

无论从哪个工作目录启动 bot，路径都解析到插件自身位置：

| 启动位置 | CWD | 解析后的 download_path |
|---------|-----|----------------------|
| 项目根目录 | `E:\wzs\github-repo\SSBot` | `E:\wzs\github-repo\SSBot\src\plugins\jm_downloader\data\downloads` |
| 其他目录 | `C:\Users\xxx` | `E:\wzs\github-repo\SSBot\src\plugins\jm_downloader\data\downloads` |

---

## 完整搜索下载流程

### 流程图

```
用户发送 /jm_search {关键词}
        │
        ▼
┌─ command_search.py: handle_jm_search ──────────────────────┐
│ 1. 提取关键词                                               │
│ 2. 发送"搜索中"提示                                         │
│ 3. 调用 JmDownloaderService.search_comics(keyword)         │
│    └─ JmApi.search_comics(keyword)                         │
│       └─ client.search_site(search_query=keyword, page=1)  │
│       └─ 返回 [{id, title, tags}, ...]（最多5条）            │
│ 4. 存储结果到 StateManager（key = (group_id, user_id)）     │
│ 5. 发送搜索结果列表（带序号）                                 │
│ 6. handler 结束，不 pause                                   │
└────────────────────────────────────────────────────────────┘
        │
        │  用户看到列表后发送数字（如 "3"）
        ▼
┌─ command_search.py: handle_jm_selection ───────────────────┐
│ 1. Rule: _has_active_session 检查是否有活跃会话              │
│    └─ 无会话 → 不处理，消息放行（block=False）                │
│    └─ 有会话 → 进入 handler                                 │
│                                                             │
│ 2. 解析用户输入：                                            │
│    ├─ "取消"/"cancel"/"c" → 清除会话，回复已取消              │
│    ├─ 非数字 → return（放行，让用户正常聊天）                 │
│    ├─ 数字 > 结果数量 → 提示序号无效                         │
│    └─ 有效数字 → 提取对应 comic_id                          │
│                                                             │
│ 3. 下载流程：                                                │
│    ├─ 发送"正在下载"提示                                     │
│    ├─ JmDownloaderService.download_and_convert_to_pdf(id)  │
│    │  └─ JmApi.download_raw_comic(id)                      │
│    │     └─ jmcomic.download_album(id, option)             │
│    │        ├─ 下载图片到 data/downloads/{photo_name}/     │
│    │        ├─ 图片解码并转换为 .png                         │
│    │        └─ after_album: img2pdf 插件                    │
│    │           ├─ 合并所有章节图片为 {id}.pdf                │
│    │           └─ delete_original_file: 删除原始图片         │
│    │     └─ 在 download_dir 找到 {id}.pdf                   │
│    │                                                        │
│ 4. 上传文件（按事件类型分支）：                                │
│    ├─ GroupMessageEvent → bot.upload_group_file()           │
│    └─ PrivateMessageEvent → bot.upload_private_file()       │
│                                                             │
│ 5. 清理：                                                    │
│    ├─ 清除 StateManager 会话                                │
│    └─ 根据 config.delete_after_upload 删除本地 PDF          │
└─────────────────────────────────────────────────────────────┘
```

### 直接下载流程（/jm {id}）

```
用户发送 /jm {漫画ID}
        │
        ▼
┌─ command_jm.py: handle_jm_download ────────────────────────┐
│ 1. 提取漫画 ID                                              │
│ 2. 发送"正在下载"提示                                        │
│ 3. JmDownloaderService.download_and_convert_to_pdf(id)     │
│    └─ 同上：下载 → 转 PNG → img2pdf 合并 → {id}.pdf         │
│ 4. 上传文件（群聊/私聊分支）                                  │
│ 5. 清理本地文件                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 指令参考

### 执行流程指令

| 指令 | 用途 | 示例 | 适用场景 |
|------|------|------|---------|
| `/jm_search {关键词}` | 搜索漫画 | `/jm_search 精灵` | 私聊 + 群聊 |
| `/jm_search {关键词}` 的别名 | 同上 | `/jm search 异世界` | 私聊 + 群聊 |
| `/jm {漫画ID}` | 直接下载指定漫画 | `/jm 1446575` | 私聊 + 群聊 |
| `{数字}` | 选择搜索结果中的漫画 | `3`（选择第3条） | 有活跃搜索会话时 |

### 取消/中断流程指令

| 指令 | 用途 | 适用场景 |
|------|------|---------|
| `取消` | 取消当前搜索会话 | 有活跃搜索会话时 |
| `cancel` | 同上（英文） | 同上 |
| `c` | 同上（简写） | 同上 |

### 会话超时

- 搜索会话有效期：**5 分钟**
- 超时后自动失效，用户需重新搜索
- 发送非数字消息不会取消会话（可正常聊天）

---

## Clone and Run 步骤

在新机器上从零开始运行，不需要修改任何代码或配置文件：

```bash
# 1. 克隆仓库
git clone <repo-url> SSBot
cd SSBot

# 2. 创建虚拟环境
python -m venv .venv

# 3. 安装依赖（一条命令装齐所有）
.venv\Scripts\pip install -e .

# 4. 创建环境配置
cp .env.example .env

# 5. 启动 bot
.venv\Scripts\python bot.py
```

然后配置 NapCatQQ 连接（见下方）。

### NapCatQQ 连接配置

1. 启动 NapCatQQ，打开 WebUI（默认 `http://127.0.0.1:6099`）
2. 网络配置 → 新建 → **WebSocket 客户端**
3. 填写：

| 字段 | 值 |
|------|-----|
| URL | `ws://127.0.0.1:8080/onebot/v11/ws` |
| Token | 留空 |

4. 保存并启用

### 连接成功标志

SSBot 终端输出：
```
[INFO] nonebot | OneBot V11 | Bot xxxxxxxx connected
```

---

## 配置文件说明

### .env（环境配置）

```env
DRIVER=~fastapi+~websockets   # 驱动：HTTP服务端 + WebSocket
HOST=127.0.0.1                # 监听地址
PORT=8080                     # 监听端口
ONEBOT_WS_PATH=/onebot/v11/ws # WebSocket 路径
LOG_LEVEL=DEBUG               # 日志级别
```

可通过环境变量覆盖的插件配置：

| 环境变量 | 默认值 | 说明 |
|---------|-------|------|
| `JM_DOWNLOAD_PATH` | 插件目录/data/downloads | 下载目录 |
| `JMCOMIC_OPTION_FILE` | 插件目录/data/jmcomic_options.yml | jmcomic 配置文件 |
| `JM_MAX_SEARCH_RESULTS` | 5 | 最大搜索结果数 |
| `JM_DELETE_AFTER_UPLOAD` | true | 上传后删除本地文件 |
| `JM_MAX_CONCURRENT_DOWNLOADS` | 3 | 最大并发下载数 |

### jmcomic_options.yml（功能模板）

此文件**不含路径配置**，仅定义功能行为：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `download.image.suffix` | `.png` | 下载后转换为 PNG |
| `download.image.decode` | `true` | 解密图片 |
| `download.threading.image` | 30 | 图片下载线程数 |
| `plugins.valid` | `[log, img2pdf]` | 启用的插件 |
| `plugins.after_album` | img2pdf 配置 | 下载完成后合并为 PDF |
| `filename_rule` | `Aid` | PDF 用漫画 ID 命名 |
| `delete_original_file` | `true` | 生成 PDF 后删除原始图片 |

---

## 测试参数

### 基础功能测试

| 测试编号 | 场景 | 操作 | 预期结果 | 验证点 |
|---------|------|------|---------|--------|
| T01 | 私聊搜索 | 私聊发送 `/jm_search 精灵` | 返回搜索中提示 → 返回5条结果列表 | 搜索 API 正常 |
| T02 | 私聊选择下载 | T01 后发送 `1` | 返回下载提示 → 收到 PDF 文件 | img2pdf + upload_private_file |
| T03 | 私聊取消 | T01 后发送 `取消` | 返回"已取消" | 会话清除 |
| T04 | 私聊直接下载 | 私聊发送 `/jm 1446575` | 返回下载提示 → 收到 PDF | 直接下载流程 |
| T05 | 群聊搜索 | 群聊发送 `/jm_search 精灵` | 同 T01 | 群聊触发 |
| T06 | 群聊选择下载 | T05 后发送 `3` | 同 T02 但用 upload_group_file | 群文件上传 |
| T07 | 群聊取消 | T05 后发送 `c` | 返回"已取消" | 群聊会话清除 |

### 异常场景测试

| 测试编号 | 场景 | 操作 | 预期结果 |
|---------|------|------|---------|
| E01 | 空关键词 | `/jm_search` | 提示"请提供搜索关键词" |
| E02 | 无效序号 | 搜索后发送 `99` | 提示"序号无效" |
| E03 | 负数序号 | 搜索后发送 `-1` | 消息放行（不处理） |
| E04 | 非数字消息 | 搜索后发送 `你好` | 消息放行（用户可正常聊天） |
| E05 | 无活跃会话 | 直接发送 `1`（未搜索过） | 消息放行 |
| E06 | 不存在的漫画 ID | `/jm 999999999` | 返回错误提示 |
| E07 | 会话超时 | 搜索后等待 5 分钟再选择 | 会话已失效，消息放行 |

### 多用户隔离测试

| 测试编号 | 场景 | 操作 | 预期结果 |
|---------|------|------|---------|
| M01 | 群聊多用户同时搜索 | 用户A `/jm_search 精灵`，用户B `/jm_search 魔法` | 各自收到不同的结果列表 |
| M02 | 群聊多用户同时选择 | 用户A 发送 `1`，用户B 发送 `2` | 各自下载对应的漫画，不串 |
| M03 | 同用户多群搜索 | 用户A 在群1和群2同时搜索 | 两群会话独立，不串 |

### 可移植性测试

| 测试编号 | 场景 | 操作 | 预期结果 |
|---------|------|------|---------|
| P01 | 从项目根目录启动 | `cd SSBot && python bot.py` | 正常启动，下载文件在插件 data/downloads/ |
| P02 | 从其他目录启动 | `cd C:\ && python E:\...\SSBot\bot.py` | 同上，路径不受 CWD 影响 |
| P03 | 新机器 clone | clone → pip install -e . → cp .env.example .env → run | 全程不需修改代码 |

### 文件验证

下载完成后检查：

```bash
# PDF 应在插件目录下，名为 {comic_id}.pdf
ls src/plugins/jm_downloader/data/downloads/
# 预期：1446575.pdf（不应有 webp 文件或子文件夹残留）

# 项目根目录不应有下载的文件
ls *.pdf *.webp 2>/dev/null  # 预期：无输出
```

---

## 文件结构

```
SSBot/
├── .env.example              # 环境配置模板
├── .env                      # 实际环境配置（从 .env.example 复制，不入版本控制）
├── .env.dev                  # 开发环境覆盖配置
├── .gitignore                # 版本控制忽略规则
├── bot.py                    # NoneBot2 入口
├── pyproject.toml            # 项目依赖声明
├── JM_SEARCH_FLOW.md         # 搜索下载流程文档
├── JM_PORTABLE_ARCH.md       # 本文档：可移植架构与流程
└── src/plugins/jm_downloader/
    ├── __init__.py           # 插件初始化（模块级服务注入）
    ├── config.py             # 配置模型（__file__ 路径计算）
    ├── data/
    │   ├── jmcomic_options.yml  # jmcomic 功能模板（无路径）
    │   └── downloads/           # 下载目录（运行时创建，不入版本控制）
    ├── handlers/
    │   ├── command_search.py    # 搜索 + 选择 handler
    │   └── command_jm.py        # 直接下载 handler
    ├── services/
    │   ├── jm_api.py            # jmcomic API 封装（路径注入）
    │   ├── jm_downloader.py     # 下载业务逻辑
    │   └── state_manager.py     # 搜索会话状态管理
    ├── builders/
    │   └── message_formatter.py # 消息格式化
    └── models/
        └── comic_data.py        # 漫画数据模型
```
