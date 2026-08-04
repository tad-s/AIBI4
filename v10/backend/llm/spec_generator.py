"""自然言語 → QuerySpec（構造化仕様）の生成。

LLM には「コード」ではなく、定義済みの指標・軸・フィルタから成る JSON 仕様を
出力させる。曖昧な依頼は clarify、データにない軸を求める依頼は impossible を返す。
生成された spec は pydantic で検証してからエンジンに渡す。
"""
from __future__ import annotations

import json

from openai import OpenAI

from core.config import settings
from semantic.model import DIMENSIONS, METRICS
from semantic.query import QuerySpec

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _system_prompt(meta: dict) -> str:
    def _syn(obj) -> str:
        return f'（同義語: {"、".join(obj.synonyms)}）' if obj.synonyms else ""

    metrics_desc = "\n".join(
        f'  - "{m.id}": {m.label}（単位:{m.unit or "—"}, base:{m.view}） {m.description}{_syn(m)}'
        for m in METRICS.values()
    )
    dims_desc = "\n".join(
        f'  - "{d.id}": {d.label}（利用可: {"/".join(d.views)}）{_syn(d)}'
        for d in DIMENSIONS.values()
    )
    stores = meta.get("stores", [])
    months = meta.get("months", [])
    cats = meta.get("categories", [])

    return f"""あなたは飲食チェーンのBIアシスタントです。
ユーザーの自然言語の依頼を、下記の「指標(metric)」「軸(dimension)」「フィルタ(filter)」だけを
使った分析仕様(JSON)に変換します。生SQLやコードは出力しません。

【指標 metric（1つ選ぶ）】
{metrics_desc}

【軸 dimension（0〜2個。base の整合性に注意）】
{dims_desc}

★重要な制約:
- base が "orders" の指標（客単価/注文数/平均人数/一人単価/平均滞在時間/平均注文点数/ドリンク比率）は、
  軸 "category"（商品カテゴリ）や "item"（商品）と組み合わせられません。
  例:「カテゴリ別の客単価」は不可 → clarify で売上など商品単位の指標を提案してください。
- 売上(revenue)・販売点数(quantity)は全ての軸と組み合わせ可能です。

【フィルタ filter に使える実データ値】
- 店舗(stores): {", ".join(map(str, stores[:40])) or "（なし）"}
- 月(months): {", ".join(map(str, months)) or "（なし）"}
- カテゴリ(categories): {", ".join(map(str, cats)) or "（なし）"}
- 時間帯は hour_min/hour_max（0-23の整数）、曜日は dow（0=月〜6=日）で指定。

【出力仕様】必ず次の JSON だけを返す（前後に文章を付けない）:
{{
  "action": "query" | "clarify" | "impossible",
  "message": "ユーザーへの一言（queryなら分析の要約、clarify/impossibleなら質問や説明）",
  "confidence": 0.0〜1.0,   // 依頼を指標・軸・フィルタに正しく写像できた確信度（queryのとき必須。曖昧・推測が多いほど低く）
  "spec": {{
    "metric": "<metric id>",
    "dimensions": ["<dim id>", ...],
    "filters": {{
      "months": [], "stores": [], "categories": [], "customer_layers": [],
      "weather": [], "hour_min": null, "hour_max": null, "dow": []
    }},
    "chart_type": "kpi|bar|line|area|pie|table",
    "sort": "value_desc|value_asc|dim_asc",
    "limit": 20,
    "title": "グラフのタイトル"
  }}
}}

判断基準:
- 依頼が明確 → action="query"。適切な指標・軸・フィルタ・グラフ種別を埋める。
  時系列(月/日付)は "line" かつ sort="dim_asc"、構成比は "pie"、ランキングは "bar"+"value_desc"。
- 指標や軸が曖昧で複数解釈できる → action="clarify"。spec は null 可。何を確認したいか message に書く。
- データに無い属性（年齢/性別/会員/リピート/個人情報など）を要求 → action="impossible"。
  message で理由と、店舗別/商品別/時間帯別/客単価などの代替案を提示する。
- フィルタの店舗名・カテゴリ名は、上記の実データ値に最も近いものへ正規化して使う。
"""


def generate(user_text: str, meta: dict, history: list[dict] | None = None) -> dict:
    """{"action","message","spec"(dict|None),"error"?} を返す。"""
    messages = [{"role": "system", "content": _system_prompt(meta)}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_text})

    try:
        resp = _get_client().chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        return {"action": "clarify",
                "message": f"うまく解釈できませんでした。もう少し具体的に指定してください。（{e}）",
                "spec": None}

    action = data.get("action", "clarify")
    message = data.get("message", "")

    if action != "query":
        return {"action": action, "message": message, "spec": None}

    # spec を pydantic で検証
    try:
        spec = QuerySpec.model_validate(data.get("spec") or {})
    except Exception as e:
        return {"action": "clarify",
                "message": "分析の指定が不完全でした。指標や軸をもう少し具体的に教えてください。",
                "spec": None, "error": str(e)}

    # 確信度（0〜1 に丸める。欠損時は None）
    confidence = data.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None

    return {"action": "query", "message": message,
            "spec": spec.model_dump(), "confidence": confidence}
