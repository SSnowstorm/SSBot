from nonebot.adapters.onebot.v11 import Bot
from pathlib import Path
from ..utils.logger import logger


class QQUploader:
    @staticmethod
    async def upload_pdf(bot: Bot, group_id: int, file_path: Path) -> bool:
        try:
            if not file_path.exists():
                logger.error(f"文件不存在: {file_path}")
                return False

            await bot.upload_group_file(
                group_id=group_id,
                file=str(file_path),
                name=file_path.name
            )
            return True

        except Exception as e:
            logger.error(f"上传失败: {e}")
            return False
