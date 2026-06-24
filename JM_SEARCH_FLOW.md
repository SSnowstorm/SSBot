# JM Downloader 搜索功能流程文档

## 概述

本文档描述 `jm_downloader` 插件的搜索下载完整流程，包括执行指令、取消/终止指令、测试参数。

支持 **私聊** 和 **群聊** 两种场景，共用同一套搜索→选择→下载流程，仅在文件上传环节分叉。

---

## 一、流程图

```
用户发送 /jm_search {关键词}
        │
        ▼
┌─────────────────────────────────┐
│  handler 接收 MessageEvent       │
│  (GroupMessageEvent /            │
│   PrivateMessageEvent 均可进入)   │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  调用 jmcomic client.search_site │
│  获取搜索结果列表                  │
│  返回 [(id, title, tags), ...]   │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  格式化结果列表，发送到聊天        │
│  session_key = (group_id,        │
│    user_id) 存入 StateManager    │
│  group_id=None 表示私聊           │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  on_message 监听后续消息          │
│  rule: 检查 session_key 是否      │
│  有活跃会话 (存在且未超时 5min)    │
│  block=False (不干扰普通聊天)     │
└──────────────┬──────────────────┘
               │
        用户回复消息
               │
       ┌───────┼───────┐
       │       │       │
       ▼       ▼       ▼
   "取消"   数字N    其他文本
       │       │       │
       ▼       ▼       ▼
   清除会话  查找结果  放行(不处理)
   回复已取消  │
              │
       ┌──────┴──────┐
       │             │
       ▼             ▼
    序号有效       序号无效
       │             │
       ▼             ▼
   提取comic_id   回复"输入无效"
   开始下载
       │
       ▼
┌─────────────────────────────────┐
│  下载完成，准备上传文件           │
│  isinstance 判断事件类型          │
└──────────────┬──────────────────┘
               │
       ┌───────┴───────┐
       │               │
       ▼               ▼
GroupMessageEvent  PrivateMessageEvent
       │               │
       ▼               ▼
upload_group_file  upload_private_file
       │               │
       └───────┬───────┘
               │
               ▼
┌─────────────────────────────────┐
│  清理会话状态 + 清理临时文件       │
└─────────────────────────────────┘
```

---

## 二、执行流程指令

### 2.1 搜索漫画

| 场景 | 指令 | 示例 |
|------|------|------|
| 私聊 | `/jm_search {关键词}` | `/jm_search 异世界` |
| 群聊 | `/jm_search {关键词}` | `/jm_search 无修正` |
| 别名 | `/jm search {关键词}` | `/jm search MANA` |

**流程**：
1. 机器人回复"正在搜索..."
2. 调用 jmcomic `client.search_site(search_query=关键词, page=1)`
3. 返回最多 `max_search_results`（默认5）条结果
4. 格式化为带序号的列表发送到聊天
5. 进入等待选择状态（5分钟超时）

### 2.2 选择漫画下载

| 场景 | 指令 | 示例 |
|------|------|------|
| 私聊 | 直接发送数字 | `1` |
| 群聊 | 直接发送数字 | `3` |

**流程**：
1. 从 StateManager 中取出该用户的搜索结果
2. 校验序号是否在有效范围内
3. 提取 `comic_id`，调用 `download_and_convert_to_pdf(comic_id)`
4. 下载完成后，按私聊/群聊分别调用 `upload_private_file` / `upload_group_file`
5. 上传完成后清理会话状态和临时文件

### 2.3 直接下载（无需搜索）

| 场景 | 指令 | 示例 |
|------|------|------|
| 私聊 | `/jm {id}` | `/jm 422866` |
| 群聊 | `/jm {id}` | `/jm 422866` |
| 别名 | `/JM {id}` | `/JM 422866` |

**流程**：
1. 机器人回复"正在下载..."
2. 调用 `download_and_convert_to_pdf(comic_id)`
3. 下载完成后按私聊/群聊上传文件
4. 上传完成后清理临时文件

---

## 三、取消/终止流程指令

### 3.1 取消搜索选择

在搜索结果列表发出后、选择漫画前，发送以下任一内容即可取消：

| 指令 | 说明 |
|------|------|
| `取消` | 中文取消 |
| `cancel` | 英文取消 |
| `c` | 简写取消 |

**效果**：清除会话状态，机器人回复"操作已取消。"，后续消息不再被拦截。

### 3.2 会话自动超时

- 超时时间：**5 分钟**（`StateManager.SESSION_TIMEOUT = 300` 秒）
- 超时后：会话自动失效，用户发送数字不会触发下载，需重新搜索
- 超时后发送数字：消息被放行（不触发选择 handler），不会报错

### 3.3 重新搜索覆盖

- 用户在已有活跃会话时再次发送 `/jm_search {新关键词}`
- 旧会话被自动覆盖，替换为新搜索结果
- 无需先取消再搜索

### 3.4 非数字消息放行

- 用户在有活跃会话时发送非数字、非"取消"的消息（如"你好"）
- 消息被放行，不触发选择 handler，不影响会话状态
- 用户仍可继续选择序号

---

## 四、测试参数

### 4.1 基本测试流程

#### 步骤1：私聊搜索测试

```
私聊机器人发送：
    /jm_search 异世界

预期结果：
    1. 机器人回复"正在搜索 '异世界'，请稍候..."
    2. 数秒后回复搜索结果列表（带序号）
    3. 列表末尾提示"请回复序号选择您想要下载的漫画。"
```

#### 步骤2：私聊选择测试

```
私聊机器人发送：
    1

预期结果：
    1. 机器人回复"您选择了：《xxx》(ID: xxx)，即将开始下载。"
    2. 机器人回复"正在下载漫画 ID: xxx，请稍候..."
    3. 下载完成后回复"漫画 ID: xxx 已下载完成，正在发送文件。"
    4. 机器人通过 upload_private_file 发送 PDF 文件
```

#### 步骤3：私聊取消测试

```
私聊机器人发送：
    /jm_search 测试
等待结果列表出现后发送：
    取消

预期结果：
    机器人回复"操作已取消。"
    后续发送数字不再触发下载
```

#### 步骤4：群聊搜索测试

```
在群聊中发送：
    /jm_search 异世界

预期结果：
    同步骤1，但机器人会 @发送者
```

#### 步骤5：群聊选择测试

```
在群聊中发送：
    2

预期结果：
    同步骤2，但文件通过 upload_group_file 上传到群
```

#### 步骤6：群聊多用户隔离测试

```
用户A在群聊发送：/jm_search 关键词A
用户B在群聊发送：/jm_search 关键词B
用户A发送：1
用户B发送：1

预期结果：
    用户A下载的是关键词A的第1个结果
    用户B下载的是关键词B的第1个结果
    两者互不干扰
```

### 4.2 测试用关键词

以下关键词可用于测试搜索功能（需 jmcomic 库能正常连接禁漫服务器）：

| 关键词 | 说明 |
|--------|------|
| `MANA` | 常见标签，结果较多 |
| `無修正` | 繁体标签 |
| `异世界` | 中文关键词 |
| `CG` | 短关键词 |

### 4.3 测试用漫画ID

用于 `/jm {id}` 直接下载测试：

| ID | 说明 |
|----|------|
| `422866` | 原代码中的测试ID |

### 4.4 配置参数

可通过环境变量或 NoneBot 配置文件调整：

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 下载路径 | `JM_DOWNLOAD_PATH` | `data/jm_downloader/downloads` | PDF 临时存放目录 |
| jmcomic配置 | `JMCOMIC_OPTION_FILE` | `data/jm_downloader/jmcomic_options.yml` | jmcomic 库配置文件 |
| 最大搜索结果 | `JM_MAX_SEARCH_RESULTS` | `5` | 搜索列表显示数量上限 |
| 上传后删除 | `JM_DELETE_AFTER_UPLOAD` | `True` | 上传后是否删除本地PDF |
| 最大并发下载 | `JM_MAX_CONCURRENT_DOWNLOADS` | `3` | 同时下载任务上限 |

### 4.5 会话超时参数

在 `src/plugins/jm_downloader/services/state_manager.py` 中修改：

```python
SESSION_TIMEOUT = 300  # 单位：秒，默认5分钟
```

### 4.6 异常场景测试

| 场景 | 操作 | 预期结果 |
|------|------|----------|
| 空关键词 | `/jm_search` | 回复"请提供搜索关键词" |
| 无结果 | `/jm_search zzzzznotexist` | 回复"未能找到符合条件的漫画" |
| 无效序号 | 搜索后发送 `99` | 回复"输入无效，请输入有效的序号或'取消'。" |
| 超时后选择 | 等待5分钟后发送数字 | 消息被放行，不触发下载 |
| 不存在的漫画ID | `/jm 999999999` | 回复"未找到漫画 999999999" |
| 非数字消息 | 搜索后发送 `你好` | 消息放行，会话保持活跃 |

---

## 五、文件修改清单

| 文件 | 改动内容 |
|------|----------|
| `__init__.py` | 改为模块级初始化，删除不执行的 `_plugin_on_load` |
| `services/jm_api.py` | 用真实 `client.search_site()` 替换 Mock；新增 `self._client` |
| `services/state_manager.py` | key 改为 `(group_id, user_id)` 元组；新增超时机制 |
| `builders/message_formatter.py` | 移除 `at_sender` 参数（交给 handler 的 `send(at_sender=True)`）；新增 `format_searching_message` 和 `format_session_expired_message` |
| `handlers/command_search.py` | 重写：`MessageEvent` 支持私聊；`on_message` + rule 替换 `pause()/got()`；上传分支 |
| `handlers/command_jm.py` | `GroupMessageEvent` → `MessageEvent`；上传分支支持私聊 |

---

## 六、架构说明

### 6.1 会话隔离机制

```
session_key = (group_id_or_None, user_id)

私聊场景: (None, 12345678)       → 唯一
群聊场景: (527020285, 12345678)  → 与同群其他用户隔离
         (527020285, 87654321)  → 不同用户
         (999999999, 12345678)  → 与其他群隔离
```

### 6.2 消息流转优先级

```
priority=10  /jm, /jm_search 命令 (block=True)
             ↓ 匹配失败则继续
priority=11  on_message 选择监听 (rule: 有活跃会话才触发, block=False)
             ↓ rule 不匹配则跳过
priority=12+ 其他插件的消息处理器
```

### 6.3 数据流

```
用户输入
  → handler (command_search.py)
    → JmDownloaderService.search_comics()
      → JmApi.search_comics()
        → jmcomic client.search_site()
        ← List[Dict]
      ← List[ComicInfo]
    ← List[ComicInfo]
  → StateManager.set_search_results()
  → MessageFormatter.format_search_results()
  → 发送到聊天

用户选择
  → on_message handler
    → StateManager.get_search_results()
    → JmDownloaderService.download_and_convert_to_pdf()
      → JmApi.download_raw_comic()
        → jmcomic.download_album()
      ← Path (PDF)
    ← Path
  → bot.upload_group_file() / bot.upload_private_file()
  → StateManager.clear_search_results()
  → JmDownloaderService.clean_up_download_files()
```
