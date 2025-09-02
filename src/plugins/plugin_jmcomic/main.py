import asyncio
from pathlib import Path
from core.downloader import JmcomicDownloader


async def test_download():
    downloader = JmcomicDownloader(Path("config/jmcomic_config.yml"))
    await downloader.download_album("422866")


if __name__ == "__main__":
    asyncio.run(test_download())
