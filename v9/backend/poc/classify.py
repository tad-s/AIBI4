"""商品名 → カテゴリ分類（v10 ingest/categories を移植・PoC自己完結版）。

マスタ完全一致 → ひらがな正規化 → キーワードマッチ（締め→ドリンク→揚げ物→串→
海鮮→鍋→サラダ→ヘビー→軽いつまみ）の優先順。set_master() で外部マッピングを注入。
"""
from __future__ import annotations

_DRINK_KW = [
    "ビール", "生ビール", "生中", "生大", "ハイボール", "チューハイ", "酎ハイ",
    "サワー", "レモンサワー", "梅サワー", "ワイン", "日本酒", "冷酒", "熱燗",
    "焼酎", "麦焼酎", "芋焼酎", "泡盛", "ホッピー", "カクテル", "梅酒",
    "ウーロン茶", "お茶", "緑茶", "麦茶", "コーラ", "ジュース",
    "ソフトドリンク", "ノンアルコール", "ノンアル", "ドリンク", "ソーダ",
    "ハイ", "サワ", "麦酒", "ビア", "ホッピ", "ジョッキ", "赤星", "黒ラベル",
    "ジンジャ", "カシス", "ロック", "水割", "お冷", "ジャスミン",
]
_SHIME_KW = [
    "ラーメン", "うどん", "そば", "チャーハン", "炒飯", "焼きそば",
    "おにぎり", "ご飯", "雑炊", "ちゃんぽん", "カレー",
    "焼き飯", "焼飯", "冷麺", "蕎麦", "パスタ", "ナポリタン",
    "ドリア", "オムライス", "ライス", "釜飯", "釜めし",
]
_AGEMON_KW = [
    "唐揚げ", "から揚げ", "フライドチキン", "揚げ", "揚",
    "天ぷら", "フライ", "コロッケ", "カツ", "トンカツ", "南蛮",
    "串カツ", "串揚げ",
]
_KUSHI_KW = ["焼き鳥", "焼鳥", "串焼き", "串", "つくね", "ねぎま"]
_KAISEN_KW = [
    "刺身", "刺し身", "お刺身", "刺し", "カルパッチョ", "マリネ",
    "海老", "えび", "蟹", "かに", "たこ", "いか", "イカ",
    "まぐろ", "マグロ", "サーモン", "鮭", "魚介", "ホタテ", "貝", "あさり", "牡蠣",
    "海鮮", "なめろ", "たこわさ", "いかわさ",
]
_NABE_KW = ["鍋", "おでん", "しゃぶ", "すき焼", "チゲ"]
_SALAD_KW = ["サラダ", "チョレギ"]
_HEAVY_KW = [
    "焼肉", "ステーキ", "ハラミ", "カルビ", "豚バラ", "ロース", "ネギ塩", "もも",
    "鉄板", "炒め", "煮込み", "もつ煮", "煮込", "餃子", "ピザ", "グラタン",
]
_LIGHT_KW = [
    "野菜", "枝豆", "漬物", "キムチ", "冷奴", "豆腐",
    "おひたし", "和え物", "小鉢", "酢の物",
    "アヒージョ", "ナムル", "ポテサラ", "玉子", "卵焼き", "しらす",
    "ナム", "漬け", "生ハム", "ポン酢",
]

_EXCLUDE_EXACT = {
    "モバイルオーダー", "ＭＢオーダー", "ＭＣオーダー", "ＭＡオーダー",
    "ＭＤオーダー", "モバイル宴オーダ", "お好み宴会ＦＤ", "追加の氷", "ぼとる用氷",
}

_MASTER: dict[str, str] = {}


def set_master(master: dict[str, str]) -> None:
    global _MASTER
    _MASTER = master or {}


def _normalize(name: str) -> str:
    return "".join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in name)


def _match(name: str, kw_list: list[str]) -> bool:
    return any(kw in name for kw in kw_list)


def classify(name) -> str:
    if name is None:
        return "その他"
    s = str(name)
    if s in _EXCLUDE_EXACT:
        return "除外"
    if s in _MASTER:
        return _MASTER[s]
    n = _normalize(s)
    if _match(n, _SHIME_KW):   return "締め"
    if _match(n, _DRINK_KW):   return "ドリンク"
    if _match(n, _AGEMON_KW):  return "揚げ物"
    if _match(n, _KUSHI_KW):   return "串"
    if _match(n, _KAISEN_KW):  return "海鮮"
    if _match(n, _NABE_KW):    return "鍋"
    if _match(n, _SALAD_KW):   return "サラダ"
    if _match(n, _HEAVY_KW):   return "ヘビー"
    if _match(n, _LIGHT_KW):   return "軽いつまみ"
    return "その他"
