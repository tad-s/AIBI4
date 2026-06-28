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
    if "商品名" in df.columns:
        items = df["商品名"].dropna().unique().tolist()
        buf.append(f"商品種類数: {len(items)}")
        buf.append(f"商品一覧（全{len(items)}種）: {', '.join(map(str, items))}")
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


_INFO_QUERY_RE = re.compile(
    r"は何がありますか|何がある|を教えて|一覧|リスト|どんな.{0,6}(商品|メニュー|店舗)|"
    r"(商品|メニュー|店舗).{0,6}(何|どんな|どのような|種類)|どのような|何種類|何店舗"
)

def build_fuzzy_context(df: pd.DataFrame, user_text: str) -> tuple[str, str]:
    """ユーザーテキストの店舗/商品名を補正し、(patched_text, extra_system) を返す。"""
    if _INFO_QUERY_RE.search(user_text):
        return user_text, ""
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
        # ローカルファイル読み込みを除去（df は既にメモリ上にある）
        if re.search(r'pd\.read_csv\s*\(|pd\.read_excel\s*\(|open\s*\(', s):
            cleaned.append("# [removed: file read blocked — use df variable]")
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
            # ax.text()で追加された「データなし」などのテキストも有効なコンテンツとして扱う
            if (getattr(ax, "texts", None) and len(ax.texts) > 0):
                return True
        return False
    except Exception:
        return True


def exec_graph_code(code: str, df: pd.DataFrame) -> dict:
    """LLM生成コードを実行し {"image_b64": str, "text_output": str} または {"error": str} を返す。
    print()の出力は text_output として返す（集計結果テキスト表示に使用）。
    スレッドセーフのため sys.stdout ではなくカスタム print 関数を注入する。
    """
    plt.close("all")

    # カスタム print でコード内の出力をキャプチャ（sys.stdout を汚染しない）
    output_lines: list[str] = []

    def _captured_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        output_lines.append(sep.join(str(a) for a in args) + end)

    safe_globals = {
        "pd": pd, "np": np, "plt": plt, "matplotlib": matplotlib,
        "df": df.copy(), "print": _captured_print,
    }
    result: dict = {}

    try:
        cleaned = sanitize_code(code)
        exec(cleaned, safe_globals, {})  # noqa: S102
    except Exception as e:
        tb = traceback.format_exc()
        result = {"error": str(e), "traceback": tb}

    text_output = "".join(output_lines).strip()

    if not result:
        fig = plt.gcf()
        try:
            if _fig_has_content(fig):
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
                buf.seek(0)
                result = {"image_b64": base64.b64encode(buf.read()).decode()}
            else:
                result = {"error": "グラフが描画されませんでした（データ0件の可能性があります）。"}
        except Exception as e:
            result = {"error": str(e)}

    plt.close("all")
    if text_output:
        result["text_output"] = text_output
    return result


def call_llm_chat(summary_text: str, chat_history: list[dict],
                  extra_system: str = "") -> str:
    system_prompt = (
        "あなたは売上データに関するチャットアシスタントです。\n"
        "取得済みの売上データのサマリーは以下の通りです。\n"
        "==== データサマリー ====\n"
        f"{summary_text}\n"
        "=======================\n\n"
        "【絶対禁止事項】\n"
        "・pd.read_csv() / pd.read_excel() / open() などでファイルを読み込んではいけない\n"
        "・データは既に変数 df としてメモリ上に読み込まれている。必ず df をそのまま使うこと\n\n"
        "【質問の種類による回答方針】\n"
        "■ グラフ不要な質問（以下に完全に該当する場合のみ）はテキストのみで回答し、コードブロックは出力しないこと：\n"
        "  - 商品名・店舗名の単純な列挙確認（「どんな商品がありますか」「店舗一覧を見せて」など）\n"
        "  - データの件数・構造・列定義の確認（「何行ありますか」「どんな列がありますか」など）\n"
        "  - 「セット商品は？」「どんなメニューがある？」などの一覧確認\n"
        "  - この場合、[AUTO_ANNOTATION] の補正情報は無視してよい\n"
        "  ※「お勧め」「人気」「ランキング」「売れ筋」「上位」「比較」「分析」を含む質問は\n"
        "    たとえ「〜を教えて」という形でも必ず集計・グラフを行うこと\n"
        "\n■ ランキング・お勧め・人気・売れ筋など集計を伴う質問（「お勧め商品を教えて」など）：\n"
        "  コードは1つのブロックにまとめ、以下の順で書くこと：\n"
        "  STEP 1: print() で集計結果を番号付きリスト形式で出力する（df.to_string()などスペース揃えの表は使わない）\n"
        "    正しい例:\n"
        "      top_qty = df.groupby('商品名')['数量'].sum().nlargest(5)\n"
        "      print('■ 売上数量 上位5商品:')\n"
        "      for i, (name, qty) in enumerate(top_qty.items(), 1):\n"
        "          print(f'{i}. {name}: {qty:,.0f}個')\n"
        "  STEP 2: 同じブロック内で上位3〜10商品のバーチャートを1枚描画する\n"
        "  ※ print()の出力はユーザーに直接表示されるので番号付きリスト形式にすること\n"
        "  ※ コードブロックの前後にテキストで結果の解釈・示唆を2〜3行書くこと\n"
        "\n■ トレンド・比較・時系列分析など通常のグラフ分析：\n"
        "  - 1〜2個のグラフを作成し、気づき（箇条書き2〜3個）と追加分析案（1〜2個）を含める\n"
        "  - 店舗別などカテゴリが多すぎる場合は売上上位10〜20に絞る\n"
        "  - グラフ描画コードは必ず ```python ... ``` に入れる\n"
        "・分析条件が明確な場合は、dfから自分で件数や集計を計算する。\n"
        "・分析条件が曖昧、候補が複数、またはデータ構造上不可能な場合は、無理にグラフ化せず確認質問または代替案をテキストで返す。\n"
        "・メッセージ末尾に [AUTO_ANNOTATION] が付く場合はグラフ分析時のみ最優先で使う。\n"
        "【コードのルール（重要）】\n"
        "・pandas 2.0+ 使用中。Series.append() / DataFrame.append() は廃止。pd.concat() を使うこと。\n"
        "・np（numpy）は利用可能。\n"
        "・各クエリのコードは毎回クリーンな df から独立して実行される。\n"
        "  前のクエリで追加した year / month 等の派生列は df に存在しない。\n"
        "  必ず df['注文日時'] や df['来店時間'] から .dt.year / .dt.month / .dt.to_period('M') で計算すること。\n"
        "・groupby().unstack() でMultiIndex列になった場合は .droplevel(0, axis=1) や .xs() で列を取り出してから使うこと。\n"
        "  例: pivot = df.groupby(['year','month'])['売上'].sum().unstack('year')  # 列は年のみ\n"
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
