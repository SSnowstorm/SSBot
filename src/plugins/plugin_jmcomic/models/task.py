from dataclasses import dataclass
from typing import Optional


@dataclass
class DownloadTask:
    album_id: str
    requester_id: int
    group_id: Optional[int] = None

    def validate(self) -> bool:
        return self.album_id.isdigit() and len(self.album_id) == 6