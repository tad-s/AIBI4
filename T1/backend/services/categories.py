"""T1 PoC用の商品分類。"""
from __future__ import annotations

_DRINK_KW = [
    "ビール", "生ビール", "ハイボール", "チューハイ", "酎ハイ", "サワー",
    "ワイン", "日本酒", "冷酒", "熱燗", "焼酎", "麦焼酎", "芋焼酎",
    "泡盛", "ホッピー", "梅酒", "カクテル", "ウーロン茶", "緑茶",
    "お茶", "コーラ", "ジュース", "ソフトドリンク", "ノンアル", "ソーダ",
    "ハイ", "サワ", "ビア", "ホッピ", "ジョッキ", "赤星", "黒ラベル",
    "ジンジャ", "カシス", "ロック", "水割", "お冷", "ジャスミン",
]
_SHIME_KW = ["ラーメン", "うどん", "そば", "蕎麦", "焼きそば", "ご飯", "ライス", "おにぎり", "雑炊", "ちゃんぽん"]
_FRIED_KW = ["唐揚げ", "から揚げ", "揚げ", "揚", "天ぷら", "フライ", "コロッケ", "カツ", "南蛮", "串カツ"]
_KUSHI_KW = ["焼き鳥", "焼鳥", "串焼き", "串", "つくね", "ねぎま"]
_SEAFOOD_KW = ["刺身", "刺し身", "刺し", "海老", "えび", "蟹", "かに", "たこ", "いか", "イカ", "まぐろ", "マグロ", "サーモン", "鮭", "牡蠣", "海鮮"]
_NABE_KW = ["鍋", "おでん", "しゃぶ", "すき焼", "チゲ"]
_SALAD_KW = ["サラダ", "チョレギ"]
_HEAVY_KW = ["焼肉", "ステーキ", "ハラミ", "カルビ", "鉄板", "炒め", "煮込み", "もつ煮", "餃子", "ピザ", "グラタン"]
_LIGHT_KW = ["枝豆", "漬物", "キムチ", "冷奴", "豆腐", "小鉢", "酢の物", "ナムル", "ポテサラ", "玉子", "卵焼き"]
_EXCLUDE_EXACT = {"モバイルオーダー", "ＭＢオーダー", "ＭＣオーダー", "ＭＡオーダー", "ＭＤオーダー", "モバイル宴オーダ"}


def _normalize(name: str) -> str:
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in str(name))


def _match(name: str, words: list[str]) -> bool:
    return any(word in name for word in words)


def classify(name) -> str:
    if name is None:
        return "その他"
    raw = str(name)
    if raw in _EXCLUDE_EXACT:
        return "除外"
    text = _normalize(raw)
    if _match(text, _SHIME_KW):
        return "締め"
    if _match(text, _DRINK_KW):
        return "ドリンク"
    if _match(text, _FRIED_KW):
        return "揚げ物"
    if _match(text, _KUSHI_KW):
        return "串"
    if _match(text, _SEAFOOD_KW):
        return "海鮮"
    if _match(text, _NABE_KW):
        return "鍋"
    if _match(text, _SALAD_KW):
        return "サラダ"
    if _match(text, _HEAVY_KW):
        return "ヘビー"
    if _match(text, _LIGHT_KW):
        return "軽いつまみ"
    return "その他"
