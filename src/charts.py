"""Biểu đồ Plotly cho khoảng giá, vết suy diễn và phân tích kho xe."""

import numpy as np
import plotly.graph_objects as go

from .presentation import BLUE, MUTED, ORANGE, TEAL, signed, vi

CHART_OPTIONS = {"displayModeBar": False, "locale": "vi"}
GRID = "#E6ECF3"


def styled(fig, height, *, x_title=None, y_title=None, margin=None):
    fig.update_layout(
        height=height, margin=margin or dict(l=8, r=12, t=13, b=12),
        font=dict(family="Inter, Arial, sans-serif", size=13, color=MUTED),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        separators=",.", showlegend=False,
        xaxis=dict(title=x_title, gridcolor=GRID, zerolinecolor=GRID, automargin=True),
        yaxis=dict(title=y_title, gridcolor=GRID, zerolinecolor=GRID, automargin=True),
        hoverlabel=dict(bgcolor="#132C4A", font_color="white", bordercolor="#132C4A"),
    )
    return fig


def price_range(valuation):
    lo, hi, price = valuation.lower, valuation.upper, valuation.price
    fig = go.Figure()
    fig.add_scatter(x=[lo, hi], y=[0, 0], mode="lines+markers",
                    line=dict(color="#B4C6DA", width=9), marker=dict(color=BLUE, size=12), hoverinfo="skip")
    fig.add_scatter(x=[price], y=[0], mode="markers", marker=dict(color=ORANGE, size=18, line=dict(color="white", width=2)),
                    hovertemplate=f"Giá đề xuất {vi(price)} triệu ₫<extra></extra>")
    for x, value, y, color in [(lo, lo, -.37, BLUE), (hi, hi, -.37, BLUE), (price, price, .38, "#AB4C14")]:
        fig.add_annotation(x=x, y=y, text=f"<b>{vi(value)}</b>", showarrow=False,
                           font=dict(color=color, size=16), yanchor="middle")
    padding = (hi - lo) * .12
    fig = styled(fig, 98, margin=dict(l=6, r=6, t=2, b=2))
    fig.update_xaxes(visible=False, fixedrange=True, range=[lo - padding, hi + padding])
    fig.update_yaxes(visible=False, fixedrange=True, range=[-.61, .65])
    return fig


def waterfall(inference):
    steps = inference.steps
    amounts = [inference.reference_price, *(step.delta for step in steps), 0]
    fig = go.Figure(go.Waterfall(
        x=["Giá mới giả định", *(step.rule_id for step in steps), "Giá theo luật"],
        y=amounts, measure=["absolute", *(["relative"] * len(steps)), "total"],
        text=[vi(amounts[0]), *(signed(step.delta) for step in steps), vi(inference.price)],
        textposition="outside", textfont=dict(color=BLUE, size=13),
        increasing=dict(marker_color=TEAL), decreasing=dict(marker_color="#7294B6"),
        totals=dict(marker_color=BLUE), connector=dict(line=dict(color="#ACBDCF", dash="dot")),
        hovertemplate="%{x}<br>%{text} triệu ₫<extra></extra>",
    ))
    styled(fig, 268, y_title="Triệu ₫")
    fig.update_yaxes(range=[0, 1.17 * max([inference.reference_price, *(step.after for step in steps)])])
    return fig


def distribution(data):
    fig = go.Figure(go.Histogram(x=data["Giá (triệu ₫)"], nbinsx=24, marker_color="#52789D",
                                hovertemplate="%{x} triệu ₫<br>%{y} xe<extra></extra>"))
    fig.update_layout(bargap=.09)
    return styled(fig, 246, x_title="Giá (triệu ₫)", y_title="Số xe")


def segment_medians(data):
    median = data.groupby("Phân khúc")["Giá (triệu ₫)"].median().sort_values()
    fig = go.Figure(go.Bar(x=median.values, y=median.index, orientation="h", marker_color="#2D6387",
                          text=[vi(price, 0) for price in median.values], textposition="outside", cliponaxis=False,
                          hovertemplate="%{y}<br>%{x:.1f} triệu ₫<extra></extra>"))
    styled(fig, 246, x_title="Trung vị (triệu ₫)", margin=dict(l=8, r=25, t=12, b=12))
    fig.update_xaxes(range=[0, median.max() * 1.20])
    return fig


def age_prices(data):
    age = data.groupby("Tuổi xe")["Giá (triệu ₫)"].median().sort_index()
    fig = go.Figure()
    fig.add_scattergl(x=data["Tuổi xe"], y=data["Giá (triệu ₫)"], mode="markers", name="Tình huống",
                     marker=dict(size=5, color="rgba(55,104,147,.24)"),
                     text=data["Dòng"], hovertemplate="%{text}<br>%{x} năm · %{y:.1f} triệu ₫<extra></extra>")
    fig.add_scatter(x=age.index, y=age.values, mode="lines+markers", name="Trung vị theo tuổi",
                    marker=dict(color=TEAL, size=5), line=dict(color=TEAL, width=2),
                    hovertemplate="Trung vị ở %{x} năm · %{y:.1f} triệu ₫<extra></extra>")
    styled(fig, 260, x_title="Tuổi xe (năm)", y_title="Triệu ₫")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", x=1, xanchor="right", y=1.1))
    fig.update_xaxes(dtick=max(1, int(np.ceil(age.index.max() / 12))))
    return fig
