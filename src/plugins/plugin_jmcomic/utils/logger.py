def logger():
    from loguru import logger
    import sys

    logger.configure(
        handlers=[
            {"sink": sys.stdout, "format": "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"},
            {"sink": "logs/jmcomic.log", "rotation": "10 MB"}
        ]
    )