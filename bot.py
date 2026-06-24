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
# nonebot.load_plugins("src/plugins/plugin_nonebot_jmcomic")  # 配置路径未指定，暂不加载

if __name__ == "__main__":
    nonebot.run()
