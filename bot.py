import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

# 初始化 NoneBot
nonebot.init(websocket_path="/onebot/v12/ws")

# 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

# 在这里加载插件
# nonebot.load_builtin_plugins("echo")  # 内置插件
# nonebot.load_plugin("thirdparty_plugin")  # 第三方插件
nonebot.load_plugins("src/plugins/plugin_nonebot_rand_qinghua")  # 本地插件
nonebot.load_plugins("src/plugins/jm_downloader")
nonebot.load_plugins("src/plugins/get_group_info")
# nonebot.load_plugins("src/plugins/plugin_nonebot_jmcomic") #0904因对应文件配置读取路径未指定屏蔽该插件导入
if __name__ == "__main__":
    nonebot.run()
