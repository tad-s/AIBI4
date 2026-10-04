"""T1 PoC用の商品分類。

DB側に商品カテゴリマスタが無いため、T1では以下の順でカテゴリを決める。
1. `T1/config/item_category_overrides.csv` の商品名完全一致
2. 商品名キーワードによる簡易分類
3. どちらにも該当しない場合は `その他`
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
OVERRIDE_CSV = CONFIG_DIR / "item_category_overrides.csv"

_DRINK_KW = [
    "ビール", "生ビール", "ハイボール", "チューハイ", "酎ハイ", "サワー",
    "ワイン", "日本酒", "冷酒", "熱燗", "焼酎", "麦焼酎", "芋焼酎",
    "泡盛", "ホッピー", "梅酒", "カクテル", "ウーロン茶", "緑茶",
    "お茶", "コーラ", "ジュース", "ソフトドリンク", "ノンアル", "ソーダ",
    "ハイ", "サワ", "ビア", "ホッピ", "ジョッキ", "赤星", "黒ラベル",
    "ジンジャ", "カシス", "ロック", "水割", "お冷", "ジャスミン",
    "グラス", "Ｇ", "銚子", "中徳", "純米", "吟醸", "獺祭", "樽酒",
    "ヒレ酒", "コーン茶", "こーひ", "コーヒー", "アルコールフリー",
]
_SHIME_KW = ["ラーメン", "うどん", "そば", "蕎麦", "焼きそば", "焼そば", "ご飯", "ライス", "おにぎり", "焼おにぎり", "チャーハン", "雑炊", "ちゃんぽん"]
_FRIED_KW = ["唐揚げ", "から揚げ", "揚げ", "揚", "天ぷら", "フライ", "コロッケ", "カツ", "南蛮", "串カツ"]
_KUSHI_KW = ["焼き鳥", "焼鳥", "串焼き", "串", "つくね", "ねぎま", "巻き"]
_SEAFOOD_KW = ["刺身", "刺し身", "刺し", "海老", "えび", "蟹", "かに", "たこ", "いか", "イカ", "まぐろ", "マグロ", "サーモン", "鮭", "牡蠣", "海鮮", "ねぎとろ", "手巻", "ほっけ", "はまぐり", "うに", "鯵", "さば", "しらす"]
_NABE_KW = ["鍋", "おでん", "しゃぶ", "すき焼", "チゲ"]
_SALAD_KW = ["サラダ", "チョレギ"]
_HEAVY_KW = ["焼肉", "ステーキ", "サイコロステ", "ステ", "ハラミ", "カルビ", "鉄板", "炒め", "煮込み", "すき煮", "もつ煮", "餃子", "ピザ", "グラタン", "チョリソー"]
_LIGHT_KW = ["枝豆", "漬物", "漬け", "お新香", "がっこ", "キムチ", "冷奴", "豆腐", "小鉢", "酢の物", "ナムル", "ポテサラ", "玉子", "卵焼き", "えいひれ", "そら豆", "コーン", "じゃがバター", "生ハム", "パリ焼"]
_DESSERT_KW = ["チョコ", "プリン", "わらび", "トースト", "ばにら", "バニラ", "アイス", "デザート"]
_EXCLUDE_EXACT = {"モバイルオーダー", "ＭＢオーダー", "ＭＣオーダー", "ＭＡオーダー", "ＭＤオーダー", "モバイル宴オーダ"}
_EXCLUDE_PREFIX = ("宴会", "宴", "Ｍ英字")
_DRINK_CATEGORIES = {"ドリンク", "日本酒", "焼酎", "ワイン", "果実酒", "ソフトドリンク"}
OVERRIDE_FIELDS = ["item_name", "category", "fd", "exclude_flag", "note"]


def _normalize(name: str) -> str:
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in str(name))


def _match(name: str, words: list[str]) -> bool:
    return any(word in name for word in words)


@lru_cache(maxsize=1)
def load_overrides() -> dict[str, tuple[str, str]]:
    overrides: dict[str, tuple[str, str]] = {}
    if not OVERRIDE_CSV.exists():
        return overrides
    with OVERRIDE_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item_name = (row.get("item_name") or "").strip()
            if not item_name:
                continue
            exclude_flag = (row.get("exclude_flag") or "").strip().lower() in {"1", "true", "yes", "y"}
            category = "除外" if exclude_flag else (row.get("category") or "その他").strip()
            fd = (row.get("fd") or _fd_from_category(category)).strip()
            overrides[item_name] = (category, fd)
    return overrides


def clear_overrides_cache() -> None:
    load_overrides.cache_clear()


def fd_from_category(category: str) -> str:
    return _fd_from_category(category)


def upsert_override(item_name: str, category: str, fd: str | None = None, note: str = "ユーザー編集") -> dict:
    item_name = str(item_name or "").strip()
    category = str(category or "").strip()
    if not item_name:
        raise ValueError("商品名が空です。")
    if not category:
        raise ValueError("カテゴリが空です。")

    fd_value = str(fd or _fd_from_category(category)).strip()
    if fd_value not in {"フード", "ドリンク"}:
        fd_value = _fd_from_category(category)
    exclude_flag = category == "除外"

    rows: list[dict] = []
    if OVERRIDE_CSV.exists():
        with OVERRIDE_CSV.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

    updated = False
    normalized = {
        "item_name": item_name,
        "category": category,
        "fd": fd_value,
        "exclude_flag": "true" if exclude_flag else "false",
        "note": note,
    }
    for idx, row in enumerate(rows):
        if (row.get("item_name") or "").strip() == item_name:
            rows[idx] = {**{field: "" for field in OVERRIDE_FIELDS}, **row, **normalized}
            updated = True
            break
    if not updated:
        rows.append(normalized)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with OVERRIDE_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OVERRIDE_FIELDS)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in OVERRIDE_FIELDS} for row in rows])
    clear_overrides_cache()
    return normalized


def _fd_from_category(category: str) -> str:
    return "ドリンク" if category in _DRINK_CATEGORIES else "フード"


def classify_with_fd(name) -> tuple[str, str]:
    if name is None:
        return "その他", "フード"
    raw = str(name)
    override = load_overrides().get(raw)
    if override:
        return override
    if raw in _EXCLUDE_EXACT or raw.startswith(_EXCLUDE_PREFIX):
        return "除外", "フード"
    text = _normalize(raw)
    if text.startswith(_EXCLUDE_PREFIX):
        return "除外", "フード"
    if _match(text, _SHIME_KW):
        return "締め", "フード"
    if _match(text, _DRINK_KW):
        return "ドリンク", "ドリンク"
    if _match(text, _FRIED_KW):
        return "揚げ物", "フード"
    if _match(text, _KUSHI_KW):
        return "串", "フード"
    if _match(text, _SEAFOOD_KW):
        return "海鮮", "フード"
    if _match(text, _NABE_KW):
        return "鍋", "フード"
    if _match(text, _SALAD_KW):
        return "サラダ", "フード"
    if _match(text, _HEAVY_KW):
        return "ヘビー", "フード"
    if _match(text, _LIGHT_KW):
        return "軽いつまみ", "フード"
    if _match(text, _DESSERT_KW):
        return "デザート", "フード"
    return "その他", "フード"


def classify(name) -> str:
    return classify_with_fd(name)[0]
