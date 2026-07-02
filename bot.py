import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

# 初始化 NoneBot（配置通过 .env 文件读取，不要在这里传 websocket_path）
nonebot.init()

# 注册 OneBot V11 适配器
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

# 加载插件
nonebot.load_plugins("src/plugins/plugin_nonebot_rand_qinghua")
nonebot.load_plugins("src/plugins/jm_downloader")
nonebot.load_plugins("src/plugins/get_group_info")
nonebot.load_plugin("src.plugins.interactive_help")
nonebot.load_plugin("src.plugins.sv_card")
# nonebot.load_plugins("src/plugins/plugin_nonebot_jmcomic")  # 配置路径未指定，暂不加载


# ============== 插件初始化 ==============

@nonebot.get_driver().on_startup
async def init_sv_card():
    """影之诗卡牌插件启动时加载数据。"""
    try:
        from src.plugins.sv_card._cache import init_cache, _try_register_scheduler
        await init_cache()
        _try_register_scheduler()
    except Exception as e:
        nonebot.logger.error(f"影之诗卡牌数据加载失败: {e}")

if __name__ == "__main__":
    nonebot.run()
