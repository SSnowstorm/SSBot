# 交互式帮助菜单插件

基于 NoneBot2 + OneBot V11 的 QQ 卡片式帮助菜单插件。

## 功能

- 私聊 `/help` 发送卡片式帮助菜单（json 消息段）。
- `/help <分类名>` 查看分类下的命令详情（如 `/help 漫画`）。
- 菜单内容通过 `data/help_menu.yaml` 配置，支持热重载。
- 预留权限体系：普通用户 / VIP / 管理员 / 超级管理员。
- 发送失败时自动降级为纯文本。

## 当前状态

**外观版（仅展示）**：当前使用 `com.tencent.structmsg` 的 `news` 视图发送卡片外观的消息。卡片能展示标题、标签、描述文本，但**不支持按钮交互**。用户需要通过文字命令（如 `/help 漫画`）来导航子菜单。

后续若切换到 QQ 官方适配器（`nonebot.adapters.qq`），可改用 `ark + keyboard` 实现完整的按钮交互。

## 文件结构

```
src/plugins/interactive_help/
├── __init__.py              # 插件入口
├── _handler.py              # /help 命令处理与子菜单导航
├── _builder.py              # json 卡片构建与发送
├── _config.py               # YAML 配置加载/热重载
├── _models.py               # Pydantic 配置模型
├── _permission.py           # 权限等级与校验
├── _utils.py                # 工具函数（预留）
├── _router.py               # 按钮回调路由（预留，当前不使用）
├── data/
│   └── help_menu.yaml       # 菜单与权限配置
└── README.md                # 本文档
```

## 启用方式

本插件通过 `bot.py` 中的 `nonebot.load_plugin("src.plugins.interactive_help")` 注册。

确认 `.env` 中已启用超级用户（拥有 `/help_reload` 权限）：

```env
SUPERUSERS=["你的QQ号"]
```

## 命令

| 命令 | 别名 | 权限 | 说明 |
|---|---|---|---|
| `/help` | `/帮助` `/菜单` | 所有用户 | 发送主菜单卡片 |
| `/help <分类名>` | — | 所有用户 | 发送子菜单卡片（按分类 ID 或名称匹配） |
| `/help_reload` | `/重载菜单` | 管理员及以上 | 重新加载 `help_menu.yaml` |

## 配置说明

编辑 `data/help_menu.yaml`：

```yaml
menu:
  title: "SSBot 帮助菜单"
  subtitle: "点击下方分类查看功能"

  categories:
    - id: comic
      label: "漫画工具"
      style: primary       # 预留，当前 json 卡片不使用
      permission: user     # 查看该分类需要的最低权限
      items:
        - id: jm_download
          label: "/jm 下载漫画"
          type: command    # command / nav / action
          action: "jm"     # 命令名，在子菜单中会提示用户发送此命令
          permission: user

permissions:
  admins: []
  vip_users: []
  banned_users: []
```

### 字段说明

- `id`：唯一标识，不允许重复。
- `style`：按钮样式，当前 json 卡片不使用此字段，预留给后续 keyboard 版本。
- `permission`：`banned` / `user` / `vip` / `admin` / `super_admin`，权限值由低到高。
- `type`：
  - `command`：子菜单中提示用户输入对应命令。
  - `nav`：切换菜单（当前通过文字命令导航）。
  - `action`：内置动作（预留）。

### 权限来源

1. **超级管理员**：`.env` 中 `SUPERUSERS` 列表的用户自动为 `super_admin`。
2. **管理员 / VIP / 黑名单**：在 `help_menu.yaml` 的 `permissions` 中配置。
3. **普通用户**：未在任何列表中的用户。

## 子菜单导航

由于 json 卡片不支持按钮交互，子菜单通过文字命令导航：

- `/help 漫画` → 显示漫画工具分类下的命令列表
- `/help comic` → 同上（支持按 ID 匹配）
- `/help 游戏` / `/help games` → 显示娱乐游戏分类

## 降级机制

发送 json 卡片时，如果 NapCat 不支持 `json` 消息段或发送失败，会自动降级为纯文本消息（提取卡片中的标题和描述文本直接发送）。

## 扩展方向

### 1. 切换到 QQ 官方适配器实现完整交互

将 `nonebot.adapters.onebot.v11` 替换为 `nonebot.adapters.qq`，改用 `MessageSegment.ark()` + `MessageSegment.keyboard()` 发送带按钮的交互式卡片。需要去 q.qq.com 申请机器人。

### 2. 插件动态注册菜单项

后续可扩展为插件在启动时调用注册函数：

```python
from interactive_help._builder import register_menu_item

register_menu_item(
    category_id="games",
    item_id="new_game",
    label="新游戏",
    type="command",
    action="newgame",
)
```

### 3. 使用更丰富的卡片格式

当前使用 `news` 视图，后续可尝试：
- XML 卡片格式（如 go-cqhttp 时代的 `layout=2` 列表卡片）
- `miniapp` 消息段（小程序卡片）
- QQ 官方的 `template_id=23` 链接+文本列表模板

## 已知限制

- json 卡片不支持按钮交互，只能展示信息，导航需通过文字命令。
- `com.tencent.structmsg` 的 `news` 视图在某些 QQ 版本上可能显示不同（有图/无图）。
- 群聊场景尚未完整测试，私聊验证通过后可扩展。
- 子菜单匹配支持分类 ID 和 label，但不支持模糊拼写。
- 空的 `preview` 字段可能导致卡片不显示图片区域（取决于 QQ 客户端版本）。

## 参考

- [QQ 官方 Bot API - 消息模板](https://bot.q.qq.com/wiki/develop/nodesdk/message/message_template.html)
- [NoneBot2 OneBot V11 适配器](https://onebot.adapters.nonebot.dev/)
- [NapCat OneBot 实现](https://napneko.github.io/onebot/)
