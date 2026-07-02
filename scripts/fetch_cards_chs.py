"""
一次性爬取《影之诗：超凡世界》中文卡牌数据。

数据源：https://shadowverse-wb.com/
- 列表：  GET /web/CardList/cardList?lang=chs
- 详情：  GET /web/CardList/card?card_id={id}&lang=chs

⚠️ 必须从大陆 IP 运行（API 端根据 IP 强制返日文，不接受 lang 头）

输出：
- data/cards_chs.json          # 完整中文卡牌数据
- data/cards_chs.partial.json  # 爬取过程中的临时缓存（断点续传用）

特性：
- 断点续传（已爬过的 card_id 跳过）
- 失败重试（最多 3 次，指数退避）
- 频率控制（默认 0.15s/张）
- 进度显示
"""

from __future__ import annotations

import json
import sys
import time
import random
from pathlib import Path
from typing import Any

import requests

BASE = "https://shadowverse-wb.com"
LIST_URL = f"{BASE}/web/CardList/cardList"
CARD_URL = f"{BASE}/web/CardList/card"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": f"{BASE}/chs/deck/cardslist/",
    "Origin": BASE,
}

# 输出路径（项目根目录下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUT_FINAL = DATA_DIR / "cards_chs.json"
OUT_PARTIAL = DATA_DIR / "cards_chs.partial.json"

# 爬取参数
RATE_LIMIT_S = 0.15
MAX_RETRIES = 3
TIMEOUT_S = 20


def _get(url: str, params: dict | None = None) -> Any:
    """带重试的 GET，统一异常处理。"""
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT_S)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                backoff = 1.5 * attempt + random.uniform(0, 0.5)
                print(f"  ! 第{attempt}次失败 {e!r}，{backoff:.1f}s 后重试")
                time.sleep(backoff)
    raise RuntimeError(f"连续{MAX_RETRIES}次失败: {last_err!r}")


def fetch_card_id_list() -> list[str]:
    """拉取所有 card_id。"""
    print(f"[1/2] 拉取 card_id 列表  {LIST_URL}")
    payload = {
        "lang": "chs",
        "battle_format": 0,
        "offset": 0,
    }
    data = _get(LIST_URL, params=payload)
    cards = data.get("data", {}).get("cards", {})

    ids: list[str] = []
    for k, v in cards.items():
        # 每个卡槽是 dict，第一个 key 才是真正的 card_id
        if isinstance(v, dict) and v:
            first_real_id = next(iter(v.keys()))
            ids.append(first_real_id)
        elif isinstance(v, (str, int)):
            ids.append(str(v))

    ids = sorted(set(ids))
    print(f"  → 拿到 {len(ids)} 个 card_id（区间 {min(ids) if ids else '-'} ~ {max(ids) if ids else '-'}）")
    return ids


def fetch_card_detail(card_id: str) -> dict | None:
    """拉取单卡详情，失败返 None。"""
    try:
        data = _get(CARD_URL, params={"lang": "chs", "card_id": card_id})
    except Exception as e:
        print(f"  ✗ {card_id} 最终失败: {e}")
        return None

    details = data.get("data", {}).get("card_details", {})
    return details.get(str(card_id))


def normalize(card: dict, card_id: str) -> dict:
    """把官方 JSON 标准化成插件可直接读的结构。"""
    common = card.get("common", {}) or {}
    return {
        "card_id": int(card_id),
        "name": common.get("name", ""),
        "cost": common.get("cost"),
        "atk": common.get("atk"),
        "life": common.get("life"),
        "class_id": common.get("clan"),
        "class_name": _class_name(common.get("clan")),
        "type_id": common.get("type"),
        "type_name": _type_name(common.get("type")),
        "rarity_id": common.get("rarity"),
        "rarity_name": _rarity_name(common.get("rarity")),
        "skill_text": common.get("skill_text", "") or "",
        "evo_skill_text": common.get("evo_skill_text", "") or "",
        "flavour_text": common.get("flavour_text", "") or "",
        "cv": common.get("cv", "") or "",
        "illustrator": common.get("illustrator", "") or "",
        "card_set_id": common.get("card_set_id"),
        "tribes": common.get("tribes", []) or [],
        "image_url": f"{BASE}/uploads/card_image/chs/card/{common.get('base_card_image_id','')}.png",
    }


_CLASS_MAP = {
    0: "中立", 1: "精灵", 2: "皇家", 3: "妖精",
    4: "龙", 5: "死灵", 6: "主教", 7: "复仇者",
}
_TYPE_MAP = {
    1: "随从", 2: "咒术", 3: "增幅", 4: "护符",
}
_RARITY_MAP = {
    1: "铜", 2: "银", 3: "金", 4: "虹",
}


def _class_name(cid): return _CLASS_MAP.get(cid, str(cid) if cid is not None else "")
def _type_name(tid): return _TYPE_MAP.get(tid, str(tid) if tid is not None else "")
def _rarity_name(rid): return _RARITY_MAP.get(rid, str(rid) if rid is not None else "")


def load_partial() -> dict[str, dict]:
    """读 partial 缓存。"""
    if OUT_PARTIAL.exists():
        try:
            with OUT_PARTIAL.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ! partial 读取失败: {e}，从空开始")
    return {}


def save_partial(data: dict[str, dict]) -> None:
    """写 partial 缓存。"""
    tmp = OUT_PARTIAL.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(OUT_PARTIAL)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 自检：先单卡一次，确认能拿到中文
    print("[自检] 拉取 1 张卡确认中文...")
    sample = fetch_card_detail("10103110")
    if not sample:
        print("❌ 自检失败：单卡接口都拉不到。请检查网络或 IP。")
        return 1
    sample_name = sample.get("common", {}).get("name", "")
    print(f"  样本 card_id=10103110 name='{sample_name}'")
    if not any('\u4e00' <= ch <= '\u9fff' for ch in sample_name):
        print("⚠️ 拿到的不是中文（IP 可能不在大陆）。继续爬将全是日文，确认继续？")
        ans = input("  输入 yes 继续，其他键退出: ").strip().lower()
        if ans != "yes":
            print("已退出。")
            return 2

    ids = fetch_card_id_list()
    if not ids:
        print("❌ 没拿到任何 card_id")
        return 1

    cache = load_partial()
    print(f"[2/2] 详情爬取  共 {len(ids)} 张，缓存 {len(cache)} 张")

    todo = [cid for cid in ids if cid not in cache]
    if not todo:
        print("  全部已完成（缓存已覆盖）")
    else:
        print(f"  待爬 {len(todo)} 张，预计 {len(todo) * RATE_LIMIT_S / 60:.1f} 分钟")
        t0 = time.time()
        for i, cid in enumerate(todo, 1):
            card = fetch_card_detail(cid)
            if card:
                cache[cid] = normalize(card, cid)
            else:
                cache[cid] = {"card_id": int(cid), "_fetch_failed": True}
            if i % 10 == 0 or i == len(todo):
                elapsed = time.time() - t0
                eta = elapsed / i * (len(todo) - i)
                print(f"  [{i:>4}/{len(todo)}] {cid}  剩余 {eta/60:.1f}min")
            save_partial(cache)  # 每张都落盘，断点安全
            time.sleep(RATE_LIMIT_S + random.uniform(0, 0.1))

    # 写最终文件
    final = {cid: c for cid, c in cache.items() if not c.get("_fetch_failed")}
    failed = [cid for cid, c in cache.items() if c.get("_fetch_failed")]
    final["_meta"] = {
        "version": 1,
        "source": BASE,
        "total": len(final) - 1,  # 去掉 _meta
        "failed_ids": failed,
        "lang": "chs",
    }
    with OUT_FINAL.open("w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成。")
    print(f"  成功: {len(final) - 1} 张")
    print(f"  失败: {len(failed)} 张")
    if failed:
        print(f"  失败列表（可重跑，已记录在 _meta.failed_ids）: {failed[:10]}{'...' if len(failed) > 10 else ''}")
    print(f"  输出: {OUT_FINAL}")
    print(f"  缓存: {OUT_PARTIAL}（可保留做断点续传，也可删）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
