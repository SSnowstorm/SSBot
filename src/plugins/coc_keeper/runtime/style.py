"""KP 风格档位：宽松 / 标准 / 残酷。

只影响「叙事措辞」与「卡关兜底的触发点」，不改规则判定（骰子与成败永远由代码决定）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StyleProfile:
    key: str
    label: str
    narration: str      # 给叙事模型的风格指令
    hint_at: int        # 连续几轮无进展给软提示
    tick_at: int        # 连续几轮无进展触发世界推进
    hint_prefix: str    # 提示前缀（残酷档不用“提示”二字）

    def same_as(self, other: "StyleProfile") -> bool:
        return self.key == other.key


STYLES: dict[str, StyleProfile] = {
    "lenient": StyleProfile(
        key="lenient",
        label="宽松",
        narration="叙事留有余地，允许玩家用一点巧劲过关；失败时多给可追的方向，不渲染绝望。",
        hint_at=2,
        tick_at=5,
        hint_prefix="（KP 提示）",
    ),
    "standard": StyleProfile(
        key="standard",
        label="标准",
        narration="叙事克制，按规则来；失败时给一条可追的线索，不替玩家兜底。",
        hint_at=3,
        tick_at=6,
        hint_prefix="（KP 提示）",
    ),
    "cruel": StyleProfile(
        key="cruel",
        label="残酷",
        narration="叙事冷硬，失败就是失败，代价要写出来；不主动给方向，让玩家自己承担判断。",
        hint_at=4,
        tick_at=8,
        hint_prefix="（KP 备注）",
    ),
}

DEFAULT_STYLE = STYLES["standard"]


def get_style(key: str | None) -> StyleProfile:
    return STYLES.get((key or "").strip().lower(), DEFAULT_STYLE)
