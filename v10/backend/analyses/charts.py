"""分析用の ECharts オプション生成（安全な JSON dict のみ。関数は含めない）。

数値フォーマット（円・％等）はフロント側で meta.fmt を見て注入する。
"""
from __future__ import annotations

AXIS = "#8a93a6"
GRID = "#eef1f6"
PRIMARY = "#4f7bd8"
PALETTE = ["#4f7bd8", "#22a2b8", "#f39c12", "#e05a6d", "#70ad47",
           "#9b59b6", "#e67e22", "#1abc9c", "#5d6d7e", "#c0392b"]
CATEGORY_COLORS = {
    "ドリンク": "#5b9bd5", "揚げ物": "#f39c12", "串": "#e74c3c", "海鮮": "#1abc9c",
    "鍋": "#e67e22", "サラダ": "#70ad47", "ヘビー": "#c0392b", "軽いつまみ": "#2ecc71",
    "締め": "#9b59b6", "その他": "#95a5a6",
}

_cat_axis = {"axisLine": {"lineStyle": {"color": GRID}}, "axisTick": {"show": False},
             "axisLabel": {"color": AXIS, "fontSize": 11}}
_val_axis = {"splitLine": {"lineStyle": {"color": GRID}},
             "axisLabel": {"color": AXIS, "fontSize": 11}}


def bar_h(labels, values, colors=None, color=PRIMARY):
    """横棒（ランキング系）。上位が上に来るよう反転して渡す想定。"""
    data = []
    for i, v in enumerate(values):
        c = (colors[i] if colors else color)
        data.append({"value": v, "itemStyle": {"color": c, "borderRadius": [0, 4, 4, 0]}})
    return {
        "grid": {"left": 8, "right": 40, "top": 12, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "value", **_val_axis},
        "yAxis": {"type": "category", "data": labels, **_cat_axis},
        "series": [{"type": "bar", "data": data, "barMaxWidth": 26,
                    "label": {"show": len(values) <= 15, "position": "right",
                              "color": "#6b7280", "fontSize": 10}}],
    }


def bar_v(labels, values, colors=None, color=PRIMARY):
    data = []
    for i, v in enumerate(values):
        c = (colors[i] if colors else color)
        data.append({"value": v, "itemStyle": {"color": c, "borderRadius": [4, 4, 0, 0]}})
    return {
        "grid": {"left": 8, "right": 16, "top": 16, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "category", "data": labels,
                  **_cat_axis, "axisLabel": {"color": AXIS, "fontSize": 11,
                  "interval": 0, "rotate": 30 if len(labels) > 8 else 0}},
        "yAxis": {"type": "value", **_val_axis},
        "series": [{"type": "bar", "data": data, "barMaxWidth": 40,
                    "label": {"show": len(values) <= 12, "position": "top",
                              "color": "#6b7280", "fontSize": 10}}],
    }


def dual_line(x, y1, name1, y2, name2):
    return {
        "grid": {"left": 12, "right": 12, "top": 40, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 4, "textStyle": {"color": AXIS, "fontSize": 11}},
        "xAxis": {"type": "category", "data": x, "boundaryGap": False, **_cat_axis},
        "yAxis": [
            {"type": "value", "name": name1, "position": "left",
             "nameTextStyle": {"color": "#3b6ee8"}, **_val_axis},
            {"type": "value", "name": name2, "position": "right",
             "nameTextStyle": {"color": "#e74c3c"}, "splitLine": {"show": False},
             "axisLabel": {"color": AXIS, "fontSize": 11}},
        ],
        "series": [
            {"type": "line", "name": name1, "data": y1, "yAxisIndex": 0, "smooth": True,
             "symbolSize": 6, "lineStyle": {"width": 2.5, "color": "#3b6ee8"}, "itemStyle": {"color": "#3b6ee8"}},
            {"type": "line", "name": name2, "data": y2, "yAxisIndex": 1, "smooth": True,
             "symbolSize": 6, "lineStyle": {"width": 2.5, "color": "#e74c3c"}, "itemStyle": {"color": "#e74c3c"}},
        ],
    }


def pareto(labels, values, cum_pct):
    return {
        "grid": {"left": 12, "right": 24, "top": 40, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"top": 4, "textStyle": {"color": AXIS, "fontSize": 11}},
        "xAxis": {"type": "category", "data": labels,
                  **_cat_axis, "axisLabel": {"color": AXIS, "fontSize": 10, "interval": 0, "rotate": 35}},
        "yAxis": [
            {"type": "value", **_val_axis},
            {"type": "value", "max": 100, "position": "right", "splitLine": {"show": False},
             "axisLabel": {"color": AXIS, "fontSize": 11, "formatter": "{value}%"}},
        ],
        "series": [
            {"type": "bar", "name": "売上", "data": values, "itemStyle": {"color": PRIMARY, "borderRadius": [4, 4, 0, 0]}, "barMaxWidth": 34},
            {"type": "line", "name": "累積構成比", "data": cum_pct, "yAxisIndex": 1,
             "smooth": True, "symbolSize": 5, "lineStyle": {"color": "#e05a6d", "width": 2}, "itemStyle": {"color": "#e05a6d"}},
        ],
    }


def heatmap(x_labels, y_labels, cells, max_val):
    """cells: [[x_index, y_index, value], ...]"""
    return {
        "grid": {"left": 8, "right": 12, "top": 12, "bottom": 24, "containLabel": True},
        "tooltip": {"position": "top"},
        "xAxis": {"type": "category", "data": x_labels, "splitArea": {"show": True},
                  "axisLabel": {"color": AXIS, "fontSize": 10}},
        "yAxis": {"type": "category", "data": y_labels, "splitArea": {"show": True},
                  "axisLabel": {"color": AXIS, "fontSize": 10}},
        "visualMap": {"min": 0, "max": max_val, "calculable": True, "orient": "horizontal",
                      "left": "center", "bottom": 0, "inRange": {"color": ["#eaf1fd", "#4f7bd8", "#1c3d80"]},
                      "textStyle": {"color": AXIS, "fontSize": 10}},
        "series": [{"type": "heatmap", "data": cells,
                    "label": {"show": False}, "emphasis": {"itemStyle": {"borderColor": "#333", "borderWidth": 1}}}],
    }


def scatter(points, xname, yname):
    """points: [[x, y], ...]"""
    return {
        "grid": {"left": 12, "right": 16, "top": 16, "bottom": 8, "containLabel": True},
        "tooltip": {"trigger": "item"},
        "xAxis": {"type": "value", "name": xname, "nameTextStyle": {"color": AXIS}, **_val_axis},
        "yAxis": {"type": "value", "name": yname, "nameTextStyle": {"color": AXIS}, **_val_axis},
        "series": [{"type": "scatter", "data": points, "symbolSize": 7,
                    "itemStyle": {"color": "rgba(79,123,216,0.5)"}}],
    }


def pie(labels, values):
    data = [{"name": str(l), "value": v,
             "itemStyle": {"color": CATEGORY_COLORS.get(str(l))} if CATEGORY_COLORS.get(str(l)) else {}}
            for l, v in zip(labels, values)]
    return {
        "color": PALETTE,
        "tooltip": {"trigger": "item"},
        "legend": {"type": "scroll", "bottom": 0, "textStyle": {"color": AXIS, "fontSize": 11}},
        "series": [{"type": "pie", "radius": ["42%", "70%"], "center": ["50%", "46%"],
                    "itemStyle": {"borderColor": "#fff", "borderWidth": 2, "borderRadius": 4},
                    "label": {"formatter": "{b}\n{d}%", "fontSize": 11, "color": "#4a5163"},
                    "data": data}],
    }
