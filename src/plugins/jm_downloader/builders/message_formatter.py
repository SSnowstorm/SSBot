# plugins/jm_downloader/builders/message_formatter.py
from typing import List, Optional
from nonebot.adapters.onebot.v11 import Message, MessageSegment

from ..models.comic_data import ComicInfo


class MessageFormatter:
    """
    负责将业务逻辑层的数据格式化为 Nonebot2 的 Message 对象。
    不包含任何业务逻辑，只关注消息的展示。
    """

    def format_downloading_message(self, comic_id: str, at_sender: bool = False) -> Message:
        """
        生成“正在下载”的提示消息。
        """
        msg = f"正在下载漫画 ID: {comic_id}，请稍候..."
        if at_sender:
            return MessageSegment.at(at_sender) + " " + msg
        return Message(msg)

    def format_download_success_message(self, comic_id: str) -> Message:
        """
        生成下载成功并准备发送文件的提示消息。
        """
        return Message(f"漫画 ID: {comic_id} 已下载完成，正在发送文件。")

    def format_search_results(self, results: List[ComicInfo], max_display: int) -> Message:
        """
        生成搜索结果列表消息，带有序号供用户选择。
        """
        if not results:
            return Message("抱歉，未能找到符合条件的漫画。")

        msg_parts = [
            MessageSegment.text("为您找到以下漫画：\n")
        ]

        # 限制显示数量，防止消息过长
        display_results = results[:max_display]

        for i, comic in enumerate(display_results):
            tags_str = f"[{', '.join(comic.tags)}]" if comic.tags else ""
            msg_parts.append(
                MessageSegment.text(
                    f"{i + 1}. 《{comic.title}》 - {comic.author or '未知作者'} {tags_str}\n"
                )
            )

        if len(results) > max_display:
            msg_parts.append(MessageSegment.text(f"...\n共有 {len(results)} 个结果，仅显示前 {max_display} 个。\n"))

        msg_parts.append(MessageSegment.text("\n请回复序号选择您想要下载的漫画。"))
        msg_parts.append(MessageSegment.text("\n发送 '取消' 退出选择。"))

        return Message(msg_parts)

    def format_selected_comic_info(self, comic_info: ComicInfo) -> Message:
        """
        生成用户选择漫画后的确认信息。
        """
        return Message(f"您选择了：《{comic_info.title}》(ID: {comic_info.id})，即将开始下载。")

    def format_error_message(self, error_description: str, at_sender: bool = False) -> Message:
        """
        生成错误提示消息。
        """
        msg = f"操作失败，发生错误：{error_description}"
        if at_sender:
            return MessageSegment.at(at_sender) + " " + msg
        return Message(msg)

    def format_cancel_message(self) -> Message:
        """
        生成取消操作的提示消息。
        """
        return Message("操作已取消。")

    def format_invalid_selection_message(self) -> Message:
        """
        生成无效选择的提示消息。
        """
        return Message("输入无效，请输入有效的序号或 '取消'。")
