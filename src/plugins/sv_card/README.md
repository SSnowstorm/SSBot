# 影之诗：超凡世界 查卡器插件

基于 NoneBot2 + OneBot V11 的影之诗超凡世界（Shadowverse: Worlds Beyond）卡牌查询插件。

## 功能特性

- 🔍 **模糊搜索** - 支持按卡名、技能描述模糊搜索
- 🏷️ **职业过滤** - 支持按职业（剑/森林/龙/死/主教/魂/中立）过滤
- 🔢 **ID精确查询** - 支持按卡牌ID精确查询
- 🔄 **热重载** - 支持手动重新加载卡牌数据
- 🌐 **多语言支持** - 预留中文、英文、日文等多语言接口

## 命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/sv <关键词>` | 模糊搜索卡牌 | `/sv Albert` |
| `/sv #<职业>` | 按职业过滤 | `/sv #剑` |
| `/sv !<ID>` | 按卡牌ID精确查询 | `/sv !10124110` |
| `/sv` | 显示帮助信息 | `/sv` |
| `/sv_reload` | 重新加载卡牌数据 | `/sv_reload` |

## 数据来源

- **英文数据**: [ParticleG/shadowverse-wb-db](https://github.com/ParticleG/shadowverse-wb-db)
- **中文支持**: 可通过旅法师营地API或本地中文数据扩展

## 安装

插件已集成到 bot.py，启动时自动加载卡牌数据。

### 依赖

```
nonebot2
nonebot-adapter-onebot
httpx
```

## 配置

编辑 `src/plugins/sv_card/_config.py` 修改配置项：

```python
class SVCardConfig(BaseModel):
    # 缓存过期时间（小时）
    cache_expire_hours: int = 24

    # 搜索结果最大数量
    search_result_limit: int = 10

    # 默认语言
    default_lang: str = "en"
```

## 文件结构

```
sv_card/
├── __init__.py       # 插件入口
├── _handler.py      # 命令处理器
├── _cache.py        # 卡牌数据缓存
├── _searcher.py     # 模糊搜索算法
├── _formatter.py    # 消息格式化
└── _config.py       # 配置文件
```

## 搜索算法

1. **完整匹配** → 卡名完全相等 (100分)
2. **前缀匹配** → 卡名以关键词开头 (80分)
3. **包含匹配** → 卡名包含关键词 (60分)
4. **技能描述匹配** → 技能文本包含关键词 (30分)
5. **风味文本匹配** → 风味文本包含关键词 (15分)

## TODO

- [ ] 添加卡片图片发送功能
- [ ] 添加中文数据支持
- [ ] 添加图片格式转换（WebP → QQ兼容格式）
- [ ] 添加图片本地缓存
- [ ] 添加定时更新任务
