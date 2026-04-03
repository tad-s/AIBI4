"""
llm_service.py — OpenAI LLM 呼び出し + LLM生成コードの実行
"""
import io
import re
import base64
import traceback
import unicodedata
from difflib import get_close_matches

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openai import OpenAI
import os

_client: OpenAI | None = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini-2025-04-14")

_GRAPH_QUALITY_RULES = (
    "【グラフ品質ルール（必須）】\n"
    "・全ての金額軸のラベルには「（円）」を付ける。例: ax.set_ylabel(\"平均客単価（円）\")\n"
    "・金額の数値表示は必ず {:,} 形式でカンマ区切りにする。例: f\"{val:,.0f}円\"\n"
    "・全グラフに必ず: タイトル(set_title)・X軸ラベル(set_xlabel)・Y軸ラベル(set_ylabel) を設定する\n"
    "・バーグラフには各バーに数値アノテーションを付ける\n"
    "・天気列(temperature_2m_max/min/mean, precipitation_sum, weather_label)が存在する場合は"
    "必ずそれを使ったグラフを1つ作成する\n"
    "\n【空データ対策（必須）】\n"
    "・絞り込み後は必ず len() で件数を確認する。0件の場合は .plot() を呼ばず、"
    "ax.text(0.5, 0.5, 'データなし', ha='center', va='center', fontsize=14) で代替表示すること\n"
    "・DataFrame.plot() / Series.plot() を呼ぶ直前に if data.empty: でガードすること\n"
    "\n【データ列の意味】\n"
    "・合計金額(税込): 伝票合計（客単価）\n"
    "・単価: 1商品の販売価格\n"
    "・数量: 商品数量\n"
    "・人数: 1来店グループの人数\n"
    "・来店時間・退店時間: 実際の入退店時刻（差分が滞在時間）\n"
    "・客層: 顧客属性\n"
    "・商品名: 注文された商品名\n"
    "・通貨単位: 日本円（JPY）\n"
)


def build_data_summary(df: pd.DataFrame) -> str:
    buf = []
    buf.append(f"行数: {len(df):,}, 列数: {len(df.columns)}")
    for dt_col in ["来店時間","注文日時"]:
        if dt_col in df.columns:
            try:
                dt = pd.to_datetime(df[dt_col], errors="coerce", utc=True).dt.tz_convert("Asia/Tokyo")
                dt_min, dt_max = dt.dropna().min(), dt.dropna().max()
                if pd.notna(dt_min):
                    buf.append(f"期間: {dt_min.date()} 〜 {dt_max.date()}")
            except Exception:
                pass
            break
    if "店舗名" in df.columns:
        stores = df["店舗名"].dropna().unique().tolist()
        buf.append(f"店舗({len(stores)}店): {', '.join(map(str, stores[:20]))}")
    buf.append("\n【列情報】")
    for col in df.columns:
        non_null = df[col].notna().sum()
        line = f"- {col}: dtype={df[col].dtype}, 非null={non_null}"
        if df[col].dtype in [np.float64, np.int64, float, int]:
            try:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(s) > 0:
                    line += f", mean={s.mean():,.1f}, min={s.min():,.0f}, max={s.max():,.0f}"
            except Exception:
                pass
        buf.append(line)
    buf.append(f"\n【先頭5行のサンプル（CSV形式）】")
    buf.append(df.head(5).to_csv(index=False))
    return "\n".join(buf)


def _normalize(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    out = []
    for ch in s:
        if "\u3041" <= ch <= "\u3096":
            out.append(chr(ord(ch) + 0x60))
        else:
            out.append(ch)
    s = "".join(out)
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[\s　]", "", s)


def _fuzzy_match(query: str, candidates: list[str]) -> str | None:
    if not query or not candidates:
        return None
    qn = _normalize(query)
    for c in candidates:
        if qn == _normalize(c):
            return c
    best, best_score = None, 0.0
    for c in candidates:
        cn = _normalize(c)
        if qn in cn or cn in qn:
            score = min(len(qn), len(cn)) / max(len(qn), len(cn))
            if score > best_score:
                best_score, best = score, c
    if best and best_score >= 0.45:
        return best
    norm_cands = [_normalize(c) for c in candidates]
    hit = get_close_matches(qn, norm_cands, n=1, cutoff=0.35)
    if hit:
        return candidates[norm_cands.index(hit[0])]
    return None


def build_fuzzy_context(df: pd.DataFrame, user_text: str) -> tuple[str, str]:
    """ユーザーテキストの店舗/商品名を補正し、(patched_text, extra_system) を返す。"""
    store_cands = df["店舗名"].dropna().astype(str).unique().tolist() if "店舗名" in df.columns else []
    product_cands = df["商品名"].dropna().astype(str).unique().tolist() if "商品名" in df.columns else []

    resolved_stores: dict[str, str] = {}
    resolved_products: dict[str, str] = {}

    store_tokens = re.findall(r"([^\s「」『』,。、]+店)", user_text)
    store_tokens += re.findall(r"([^\s「」『』,。、]+)(?:の売上|について|の分析|を知りたい|の売り上げ)", user_text)
    for tok in store_tokens:
        tok = tok.strip()
        best = _fuzzy_match(tok, store_cands)
        if best and best != tok:
            resolved_stores[tok] = best

    product_patterns = [
        r"([^\s「」『』]+焼き鳥)", r"([^\s「」『』]+唐揚げ)", r"([^\s「」『』]+枝豆)",
        r"([^\s「」『』]+刺身)", r"([^\s「」『』]+ビール)", r"([^\s「」『』]+ハイボール)",
        r"([^\s「」『』]+サワー)", r"([^\s「」『』]+チューハイ)",
    ]
    for pat in product_patterns:
        for tok in re.findall(pat, user_text):
            best = _fuzzy_match(tok.strip(), product_cands)
            if best and best != tok.strip():
                resolved_products[tok.strip()] = best

    auto_lines: list[str] = []
    if resolved_stores:
        auto_lines.append("【店舗名の補正】次の正式名称として扱って集計してください。")
        for src, dst in resolved_stores.items():
            auto_lines.append(f"- '{src}' は '{dst}' として扱う")
    if resolved_products:
        auto_lines.append("【商品名の補正】次の正式名称として扱って集計してください。")
        for src, dst in resolved_products.items():
            auto_lines.append(f"- '{src}' は '{dst}' として扱う")

    patched = user_text
    extra_system = ""
    if auto_lines:
        patched = user_text + "\n\n[AUTO_ANNOTATION]\n" + "\n".join(auto_lines)
        extra_system = "【AUTO_ANNOTATIONがある場合は必ずそれを優先】\n" + "\n".join(auto_lines)
    return patched, extra_system


def parse_llm_response(text: str) -> tuple[str, list[str]]:
    codes = [m.strip() for m in re.findall(r"```python(.*?)```", text, re.DOTALL)]
    text_only = re.sub(r"```python.*?```", "", text, flags=re.DOTALL).strip()
    return text_only, codes


def sanitize_code(code: str) -> str:
    cleaned = []
    for line in code.splitlines():
        s = line.strip()
        if s.startswith("import ") or s.startswith("from "):
            continue
        if "rcParams" in s and "font" in s:
            continue
        cleaned.append(line)
    code = "\n".join(cleaned)
    code = re.sub(
        r'(\w+)\.append\((\w+),\s*ignore_index\s*=\s*True\)',
        r'pd.concat([\1, \2], ignore_index=True)',
        code,
    )
    code = re.sub(
        r'(tick_params\([^)]*?),\s*ha\s*=\s*[\'"][^\'"]*[\'"]([^)]*?\))',
        r'\1\2',
        code,
    )
    font_fix = (
        "import platform as _plt_platform\n"
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "plt.rcParams['font.family'] = ['Yu Gothic','Meiryo','MS Gothic','DejaVu Sans'] "
        "if _plt_platform.system()=='Windows' else "
        "['Noto Sans CJK JP','IPAGothic','DejaVu Sans']\n"
        "plt.rcParams['axes.unicode_minus'] = False\n"
    )
    return font_fix + code


def _fig_has_content(fig) -> bool:
    try:
        for ax in (getattr(fig, "axes", None) or []):
            if (getattr(ax, "lines", None) and len(ax.lines) > 0):
                return True
            if (getattr(ax, "patches", None) and len(ax.patches) > 0):
                return True
            if (getattr(ax, "collections", None) and len(ax.collections) > 0):
                return True
            if (getattr(ax, "images", None) and len(ax.images) > 0):
                return True
        return False
    except Exception:
        return True


def exec_graph_code(code: str, df: pd.DataFrame) -> dict:
    """LLM生成コードを実行し {"image_b64": str} または {"error": str} を返す。"""
    plt.close("all")
    safe_globals = {"pd": pd, "np": np, "plt": plt, "matplotlib": matplotlib, "df": df}
    try:
        cleaned = sanitize_code(code)
        exec(cleaned, safe_globals, {})  # noqa: S102
        fig = plt.gcf()
        if _fig_has_content(fig):
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            buf.seek(0)
            return {"image_b64": base64.b64encode(buf.read()).decode()}
        else:
            return {"error": "グラフが描画されませんでした（データ0件の可能性があります）。"}
    except Exception as e:
        tb = traceback.format_exc()
        return {"error": str(e), "traceback": tb}
    finally:
        plt.close("all")


def call_llm_chat(summary_text: str, chat_history: list[dict],
                  extra_system: str = "") -> str:
    system_prompt = (
        "あなたは『売上データ分析専用』のチャットアシスタントです。\n"
        "アップロードされたデータのサマリーは以下の通りです。\n"
        "==== データサマリー ====\n"
        f"{summary_text}\n"
        "=======================\n\n"
        "ルール:\n"
        "・ユーザーの依頼に合ったグラフを1〜3個作り、次を必ず含めて返す：\n"
        "  - グラフから読み取れる具体的な気づき（箇条書き2〜3個）\n"
        "  - 追加で行うと良い分析案（箇条書き1〜2個）\n"
        "  - グラフを描画するための matplotlib 用Pythonコード（```python```ブロック）\n"
        "・店舗別などカテゴリが多すぎる場合は売上上位10〜20に絞る。\n"
        "・ユーザーに再確認を求めてはいけない。dfから自分で件数や集計を計算する。\n"
        "・メッセージ末尾に [AUTO_ANNOTATION] が付く場合はそれを最優先で使う。\n"
        "【コードのルール（重要）】\n"
        "・pandas 2.0+ 使用中。Series.append() / DataFrame.append() は廃止。pd.concat() を使うこと。\n"
        "・np（numpy）は利用可能。\n"
        + _GRAPH_QUALITY_RULES
    )
    if extra_system:
        system_prompt += "\n\n" + extra_system

    messages = [{"role": "system", "content": system_prompt}]
    for m in chat_history:
        if isinstance(m, dict) and "role" in m and "content" in m:
            messages.append({"role": m["role"], "content": m["content"]})

    resp = get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Whisper API で音声をテキストに変換する。"""
    import io as _io
    audio_file = _io.BytesIO(audio_bytes)
    audio_file.name = filename
    transcript = get_client().audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="ja",
    )
    return transcript.text
