# SuggarChat 网页配置项清单

> 版本：v1.2（2026-08-17）  
> 用途：管理系统 P3 网页阶段的字段对照清单——哪些配置项暴露到网页、用什么控件、读写权限、建议值  
> 前置文档：
>
> - [sugarchat管理与省token设计案.md](./sugarchat管理与省token设计案.md)（治理层，A1~A7 建议值来源）
> - [sugarchat管理系统设计文档.md](./sugarchat管理系统设计文档.md)（实现层，API 契约 /ai-config/api/config）  
>   依据：config.toml 实际字段（9 组）+ 设计案第 2 章建议值



---

## 0. 结论先行

- 共 **9 组 / 60+ 字段**，网页暴露 **核心可写 26 项**，**只读 3 项**（api_key 打码、matcher_function、preset），**不暴露 ~15 项**（低频/危险/内部项）
- 控件映射：布尔 → 开关，整数 → 数字输入，短文本 → 输入框，长文本/数组 → 文本域，枚举 → 下拉
- 设计案重点项（A1~A7）全部落入"核心可写"，网页默认折叠展开
- 人格文件不在此清单（走 `/prompts/{scene}` 独立 API，见管理系统设计文档 4.2）

---

## 1. 暴露分层定义

| 层       | 定义               | 网页表现                   |
| ------- | ---------------- | ---------------------- |
| 🔵 核心可写 | 日常需要调整、设计案有建议值的项 | 表单可编辑，保存走 PUT /config  |
| ⚪ 只读    | 敏感或系统内部值         | 展示但禁用输入                |
| ⚫ 不暴露   | 低频、危险或自由扩展项      | 不渲染，保留在 config.toml 原样 |

---

## 2. 配置组清单

### 2.1 顶层设置（basic）

| 配置键                      | 类型   | 当前值       | 建议值   | 分层   | 控件 | 说明                           |
| ------------------------ | ---- | --------- | ----- | ---- | -- | ---------------------------- |
| enable                   | bool | true      | 保持    | 🔵   | 开关 | 插件总开关                        |
| parse_segments           | bool | true      | 保持    | 🔵   | 开关 | 解析消息段                        |
| matcher_function         | bool | true      | 保持    | ⚪ 只读 | -  | 钩子功能开关，改动影响自定义钩子             |
| preset                   | str  | "default" | 保持    | ⚪ 只读 | -  | 预设名，切换走 `/choose_prompt` 更安全 |
| group_prompt_character   | str  | "Yuki" | 按需   | 🔵   | 下拉 | 群人格指向，选项来自 /prompts/group 已有人格，保存即热切换 |
| private_prompt_character | str  | "Yuki" | 按需   | 🔵   | 下拉 | 私聊人格指向，选项来自 /prompts/private 已有人格，保存即热切换 |

### 2.2 模型（model，对应 default_preset）

| 配置键                 | 类型   | 当前值                        | 建议值 | 分层    | 控件   | 说明                                   |
| ------------------- | ---- | -------------------------- | --- | ----- | ---- | ------------------------------------ |
| model               | str  | deepseek-chat              | 保持  | 🔵    | 下拉   | 可选 deepseek-chat / deepseek-reasoner |
| base_url            | str  | <https://api.deepseek.com> | 保持  | 🔵    | 输入框  | 自定义 API 地址                           |
| api_key             | str  | ${DEEPSEEK_API_KEY}        | 保持  | ⚪ 只读  | 打码展示 | 只显示 `sk-****后4位`，不渲染编辑框              |
| protocol            | str  | **main**                   | 保持  | ⚫ 不暴露 | -    | 内部标识                                 |
| thought_chain_model | bool | false                      | 保持  | ⚫ 不暴露 | -    | 思维链模型，个人场景用不到                        |
| multimodal          | bool | false                      | 保持  | ⚫ 不暴露 | -    | 多模态，当前模型不支持                          |

### 2.3 会话（session）

| 配置键                     | 类型   | 当前值   | 建议值 | 分层 | 控件 | 说明            |
| ----------------------- | ---- | ----- | --- | -- | -- | ------------- |
| session_control         | bool | false | 保持  | 🔵 | 开关 | 会话自动控制        |
| session_control_time    | int  | 60    | 保持  | 🔵 | 数字 | 会话窗口秒数        |
| session_control_history | int  | 10    | 保持  | 🔵 | 数字 | 窗口内保留条数       |
| session_max_tokens      | int  | 5000  | 保持  | 🔵 | 数字 | 会话累计 token 上限 |

### 2.4 自动回复（autoreply）

| 配置键           | 类型    | 当前值         | 建议值 | 分层 | 控件   | 说明                           |
| ------------- | ----- | ----------- | --- | -- | ---- | ---------------------------- |
| enable        | bool  | false       | 保持  | 🔵 | 开关   | 自动回复总开关                      |
| global_enable | bool  | false       | 保持  | 🔵 | 开关   | 全局自动回复                       |
| probability   | float | 0.01        | 保持  | 🔵 | 数字   | 触发概率 0~1                     |
| keywords      | str[] | ["at"]      | 保持  | 🔵 | 标签输入 | 触发关键词，逗号分隔                   |
| keywords_mode | enum  | starts_with | 保持  | 🔵 | 下拉   | starts_with / contains / ... |

### 2.5 功能开关（function）

| 配置键                            | 类型   | 当前值   | 建议值           | 分层    | 控件 | 说明                     |
| ------------------------------ | ---- | ----- | ------------- | ----- | -- | ---------------------- |
| chat_pending_mode              | enum | queue | 保持            | 🔵    | 下拉 | queue / drop           |
| **synthesize_forward_message** | bool | true  | **false（A5）** | 🔵    | 开关 | 合并转发展开进上下文（设计案 A5）     |
| nature_chat_style              | bool | true  | 保持            | 🔵    | 开关 | 自然聊天风格                 |
| **poke_reply**                 | bool | true  | **false（A4）** | 🔵    | 开关 | 戳一戳回复（每次戳调 LLM，设计案 A4） |
| enable_group_chat              | bool | true  | 保持            | 🔵    | 开关 | 群聊响应                   |
| enable_private_chat            | bool | true  | 保持            | 🔵    | 开关 | 私聊响应                   |
| allow_custom_prompt            | bool | true  | 保持            | 🔵    | 开关 | 允许用户设置自定义 prompt       |
| use_user_nickname              | bool | false | 保持            | 🔵    | 开关 | 回复用用户昵称                |
| chat_object_keep_count         | int  | 10    | 保持            | ⚫ 不暴露 | -  | 聊天对象保留数                |
| nature_chat_cut_pattern        | str  | 正则    | 保持            | ⚫ 不暴露 | -  | 正则模式，改错影响切句            |

### 2.6 模型参数（llm，对应 llm_config）

| 配置键                        | 类型    | 当前值            | 建议值             | 分层    | 控件  | 说明               |
| -------------------------- | ----- | -------------- | --------------- | ----- | --- | ---------------- |
| stream                     | bool  | false          | 保持              | 🔵    | 开关  | 流式输出             |
| **memory_lenth_limit**     | int   | 50             | **20~30（A3）**   | 🔵    | 数字  | 历史消息条数上限（设计案 A3） |
| **max_tokens**             | int   | 500            | **300~500（A6）** | 🔵    | 数字  | 输出上限（设计案 A6）     |
| enable_tokens_limit        | bool  | true           | 保持              | 🔵    | 开关  | 是否启用 token 上限    |
| tokens_count_mode          | enum  | bpe            | 保持              | ⚫ 不暴露 | -   | 计数模式             |
| llm_timeout                | int   | 60             | 保持              | 🔵    | 数字  | 请求超时秒数           |
| auto_retry                 | bool  | true           | 保持              | 🔵    | 开关  | 失败自动重试           |
| max_retries                | int   | 3              | 保持              | 🔵    | 数字  | 最大重试次数           |
| enable_memory_abstract     | bool  | true           | 保持              | 🔵    | 开关  | 记忆摘要             |
| memory_abstract_proportion | float | 0.15           | 保持              | 🔵    | 数字  | 摘要比例             |
| block_msg                  | str[] | ["你好，这个问题..."] | 可自定义            | 🔵    | 文本域 | 熔断兜底文案，每行一条      |

### 2.7 工具与安全（tools，对应 llm_config.tools）

| 配置键                              | 类型   | 当前值    | 建议值                  | 分层    | 控件 | 说明                    |
| -------------------------------- | ---- | ------ | -------------------- | ----- | -- | --------------------- |
| enable_tools                     | bool | false  | **false（F1，2026-08-17 已关）** | 🔵    | 开关 | 工具总开关；无自定义工具时保持关闭，否则模型会"假装用工具"复读（见设计案 3.12.4） |
| use_minimal_context              | bool | true   | 保持                   | 🔵    | 开关 | 最小上下文                 |
| **enable_report**                | bool | true   | **false 或折中（A1/A2）** | 🔵    | 开关 | 内容安全检查（最大省 token 点）   |
| **report_exclude_system_prompt** | bool | false  | **true（A2）**         | 🔵    | 开关 | 检查时排除系统提示             |
| **report_exclude_context**       | bool | false  | **true（A2）**         | 🔵    | 开关 | 检查时排除上下文              |
| report_then_block                | bool | true   | 保持                   | 🔵    | 开关 | 违规后熔断                 |
| report_invoke_level              | enum | medium | 保持                   | 🔵    | 下拉 | 检查触发级别                |
| require_tools                    | bool | false  | 保持                   | ⚫ 不暴露 | -  | 强制工具                  |
| agent_mode_enable                | bool | false  | 保持                   | 🔵    | 开关 | Agent 模式（耗 token，默认关） |
| agent_tool_call_limit            | int  | 10     | 保持                   | ⚫ 不暴露 | -  | Agent 工具调用上限          |
| agent_thought_mode               | enum | chat   | 保持                   | ⚫ 不暴露 | -  | 思考模式                  |
| agent_mcp_client_enable          | bool | false  | 保持                   | ⚫ 不暴露 | -  | MCP 客户端               |

### 2.8 用量限额（usage_limit）

| 配置键                         | 类型   | 当前值     | 建议值      | 分层    | 控件 | 说明               |
| --------------------------- | ---- | ------- | -------- | ----- | -- | ---------------- |
| **enable_usage_limit**      | bool | false   | **true** | 🔵    | 开关 | 用量限额总开关（设计案 3.3） |
| group_daily_limit           | int  | 100     | 保持       | 🔵    | 数字 | 单群每日次数           |
| user_daily_limit            | int  | 100     | 保持       | 🔵    | 数字 | 单用户每日次数          |
| group_daily_token_limit     | int  | 200000  | 保持       | 🔵    | 数字 | 单群每日 token       |
| user_daily_token_limit      | int  | 100000  | 保持       | 🔵    | 数字 | 单用户每日 token      |
| total_daily_limit           | int  | 1500    | 保持       | 🔵    | 数字 | 全局每日次数           |
| total_daily_token_limit     | int  | 1000000 | 保持       | 🔵    | 数字 | 全局每日 token       |
| global_insights_expire_days | int  | 7       | 保持       | ⚫ 不暴露 | -  | 用量统计保留天数         |

### 2.9 管理权限组（admin，v1.1 纳入网页可编辑）

| 配置键 | 类型 | 当前值 | 建议值 | 分层 | 控件 | 说明 |
|---|---|---|---|---|---|---|
| admins | int[] | [] | 按需 | 🔵 | 标签输入 | 插件级管理员 QQ 号列表（逗号分隔） |
| admin_group | int | 0 | 按需 | 🔵 | 数字 | 管理员群 ID，0 表示不限定 |
| allow_send_to_admin | bool | false | 保持 | 🔵 | 开关 | 是否允许向管理员私发消息 |

> v1.1 决策：管理员组纳入网页可编辑——管理系统网页仅内部开发人员可登录（Token 门禁），无需隔离权限管理；`SUPERUSERS` 维持 .env 单一来源，不进网页。

### 2.10 不暴露组

| 配置组 | 字段 | 分层 | 原因 |
|---|---|---|---|
| [preset_extension] | backup_preset_list、multi_modal_preset_list | ⚫ 不暴露 | 低频 |
| [cookies] | cookie、enable_cookie | ⚫ 不暴露 | 敏感字段，绝不上网页 |
| [extended] | say_after_self_msg_be_deleted、group_added_msg 等 | ⚫ 不暴露 | 低频欢迎语/擦除文案 |
| [extra] | 自由扩展 | ⚫ 不暴露 | 无固定 schema |

---

## 3. 汇总统计

| 分层      | 数量    | 分布                                                            |
| ------- | ----- | ------------------------------------------------------------- |
| 🔵 核心可写 | 29 项  | 模型 2、admin 3、会话 4、自动回复 5、功能 7、llm 8（含 A4/A5/A6）、tools 6（含 A1/A2）、限额 7、人格指向 2 |
| ⚪ 只读    | 3 项   | matcher_function、preset、api_key（打码）                                |
| ⚫ 不暴露   | ~12 项 | cookies/extended/extra/preset_extension/内部项                  |

**设计案重点项覆盖**：A1 enable_report ✅、A2 report_exclude\_* ✅、A3 memory_lenth_limit ✅、A4 poke_reply ✅、A5 synthesize_forward_message ✅、A6 max_tokens ✅、A7 人格文件（走 /prompts API）✅

---

## 4. 保存策略（PUT /config 时）

- 网页只提交"核心可写 + 只读不改"的分组；未渲染的组（⚫）在响应中原样保留，**不做覆盖**——避免误清 cookies/extra
- 实现方式：GET /config 返回全量（含 ⚫ 组但标注 `editable: false`），PUT 时后端合并，只更新 `editable: true` 的键
- api_key：前端永远拿不到明文（打码），如需更换 key 走服务器端提示"请修改 .env.dev"或预留"更新 key"专用端点（待定）
- **v1.1 决策**：`[admin]` 组（admins/admin_group/allow_send_to_admin）纳入网页可编辑——管理系统网页仅内部开发人员可登录（Token 门禁），无需隔离权限管理；`SUPERUSERS` 维持 .env 单一来源，不进网页

---

## 附录：变更记录

| 日期         | 变更内容          | 修改人             |
| ---------- | ------------- | --------------- |
| 2026-08-17 | 初版配置项清单（v1.0） | 王遵诗 / WorkBuddy |
| 2026-08-17 | v1.1：[admin] 组纳入网页可编辑（admins/admin_group/allow_send_to_admin），核心可写 24→27 项；SUPERUSERS 维持 .env 单一来源 | 王遵诗 / WorkBuddy |
| 2026-08-17 | v1.2：enable_tools 当前值更新为 false（F1 关闭，防工具复读） | 王遵诗 / WorkBuddy |
| 2026-08-18 | v1.3：配合网页样式重构——人格字数上限改为环境变量 AI_PROMPT_MAX_LENGTH 可配置（默认 2000，安全兜底 10000）；网页新增省 Token 徽标（A1~A7 项标记「推荐关闭/推荐开启/已优化」）、今日汇总卡、三区折叠、字数统计软提示 | 王遵诗 / WorkBuddy |
