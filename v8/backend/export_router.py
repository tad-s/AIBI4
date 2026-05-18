"""
export_router.py — Excel エクスポートエンドポイント
GET /api/sessions/{sid}/export  → .xlsx ダウンロード

シート構成:
  概要     — 出力日時・データ件数・店舗数など
  分析①〜⑥ — グラフ画像 + 知見・アドバイス + 集計データ表
"""
import base64
import io
from datetime import datetime

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import session as sess

router = APIRouter()

# ── スタイル定数 ──
_BLUE      = "1E40AF"
_INS_BG    = "EFF6FF"   # 知見列 (青系)
_ADV_BG    = "F0FDF4"   # アドバイス列 (緑系)
_HDR_BG    = "1E40AF"
_HDR_FG    = "FFFFFF"

_COL_W     = 56         # 知見/アドバイス列の幅
_IMG_W     = 700        # グラフ画像の表示幅 (px)
_IMG_H     = 420        # グラフ画像の表示高さ (px)
_IMG_ROWS  = 28         # 画像が占める行数 (余裕を持たせる)


def _hdr_style(ws, row: int, col: int, value: str):
    c = ws.cell(row=row, column=col, value=value)
    c.fill  = PatternFill(start_color=_HDR_BG, end_color=_HDR_BG, fill_type="solid")
    c.font  = Font(color=_HDR_FG, bold=True, size=10)
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _write_table(ws, table: list[dict], start_row: int):
    if not table:
        return
    headers = list(table[0].keys())
    for ci, h in enumerate(headers, 1):
        _hdr_style(ws, start_row, ci, h)
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = 16

    for ri, row_data in enumerate(table, start=start_row + 1):
        for ci, h in enumerate(headers, 1):
            v = row_data.get(h, "")
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.alignment = Alignment(wrap_text=True)
            if ri % 2 == 0:
                cell.fill = PatternFill(start_color="F8FAFF", end_color="F8FAFF", fill_type="solid")


def _build_excel(analyses: list[dict], df, summary_text: str) -> io.BytesIO:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # ─── 概要シート ───
    ws0 = wb.create_sheet("概要")
    ws0.column_dimensions["A"].width = 22
    ws0.column_dimensions["B"].width = 44

    ws0["A1"].value = "AIBI4 分析レポート"
    ws0["A1"].font  = Font(bold=True, size=18, color=_BLUE)
    ws0.merge_cells("A1:B1")
    ws0.row_dimensions[1].height = 32

    info = [
        ("出力日時",   datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("データ件数", f"{len(df):,} 行" if df is not None else "—"),
        ("店舗数",     f"{df['店舗名'].nunique()} 店" if df is not None and '店舗名' in df.columns else "—"),
        ("分析件数",   f"{len(analyses)} 項目"),
    ]
    for i, (k, v) in enumerate(info, start=3):
        ws0.cell(row=i, column=1, value=k).font = Font(bold=True)
        ws0.cell(row=i, column=2, value=v)

    # データサマリー（LLM 生成テキスト）
    if summary_text:
        ws0.cell(row=8, column=1, value="データサマリー").font = Font(bold=True, size=11)
        ws0.cell(row=9, column=1, value=summary_text).alignment = Alignment(wrap_text=True, vertical="top")
        ws0.merge_cells("A9:B40")
        ws0.row_dimensions[9].height = 400

    # ─── 各分析シート ───
    for a in analyses:
        title = a.get("title", "分析")
        sheet_name = title[:31]

        ws = wb.create_sheet(sheet_name)
        ws.column_dimensions["A"].width = _COL_W
        ws.column_dimensions["B"].width = _COL_W

        # タイトル
        ws["A1"].value = title
        ws["A1"].font  = Font(bold=True, size=13, color=_BLUE)
        ws.merge_cells("A1:B1")
        ws.row_dimensions[1].height = 24

        # グラフ画像
        text_row = 4  # デフォルト (画像なし)
        img_b64 = a.get("image_b64")
        if img_b64:
            try:
                img_bytes = base64.b64decode(img_b64)
                xl_img = XLImage(io.BytesIO(img_bytes))
                xl_img.width  = _IMG_W
                xl_img.height = _IMG_H
                ws.add_image(xl_img, "A3")
                text_row = 3 + _IMG_ROWS
            except Exception:
                pass

        # 知見・アドバイス ヘッダー行
        insights = a.get("insights") or []
        advice   = a.get("advice")   or []

        ins_label = ws.cell(row=text_row, column=1, value="📌 読み取れる知見")
        ins_label.font  = Font(bold=True, size=11, color=_BLUE)
        ins_label.fill  = PatternFill(start_color=_INS_BG, end_color=_INS_BG, fill_type="solid")
        ins_label.alignment = Alignment(vertical="center")
        ws.row_dimensions[text_row].height = 20

        adv_label = ws.cell(row=text_row, column=2, value="💼 アドバイス")
        adv_label.font  = Font(bold=True, size=11, color="166534")
        adv_label.fill  = PatternFill(start_color=_ADV_BG, end_color=_ADV_BG, fill_type="solid")
        adv_label.alignment = Alignment(vertical="center")

        # 知見・アドバイス 本文
        n_rows = max(len(insights), len(advice), 1)
        for j in range(n_rows):
            r = text_row + 1 + j
            ws.row_dimensions[r].height = 36
            if j < len(insights):
                c = ws.cell(row=r, column=1, value=f"・{insights[j]}")
                c.fill = PatternFill(start_color=_INS_BG, end_color=_INS_BG, fill_type="solid")
                c.alignment = Alignment(wrap_text=True, vertical="top")
            if j < len(advice):
                c = ws.cell(row=r, column=2, value=f"・{advice[j]}")
                c.fill = PatternFill(start_color=_ADV_BG, end_color=_ADV_BG, fill_type="solid")
                c.alignment = Alignment(wrap_text=True, vertical="top")

        # 集計データ表
        table = a.get("table")
        if table:
            tbl_start = text_row + n_rows + 2
            ws.cell(row=tbl_start, column=1, value="【集計データ】").font = Font(bold=True, size=11)
            _write_table(ws, table, tbl_start + 1)

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out


@router.get("/sessions/{sid}/export")
def export_excel(sid: str):
    s = sess.get_session(sid)
    if not s:
        raise HTTPException(status_code=404, detail="セッションが見つかりません。")
    analyses = s.get("analyses")
    if not analyses:
        raise HTTPException(status_code=400, detail="分析結果がありません。先に分析を実行してください。")

    df           = s.get("df")
    summary_text = s.get("summary_text", "")

    try:
        buf = _build_excel(analyses, df, summary_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel生成エラー: {e}")

    filename = f"AIBI4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
