# -*- coding: utf-8 -*-
"""
阶段5：图表生成（阶段7网页也复用本模块）
作用：用 matplotlib 把指标画成图表。
     - 每个 chart_xxx 函数"返回一张图(fig)"，由调用方决定是保存还是显示；
     - 命令行运行会把图保存为 PNG 到 output/charts；
     - 网页用 st.pyplot(fig) 直接显示。
运行：在项目根目录的终端执行  python src/charts.py

关键坑：matplotlib 默认不支持中文，中文会显示成方框。
     下面两行 rcParams 把字体设成 Windows 自带的"微软雅黑/黑体"，并修好负号。
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 不弹出图形窗口、直接把图画成文件/交给网页
import matplotlib.pyplot as plt

from data_loader import load_and_clean
from analyzer import run_all_analysis

# 中文字体（按顺序找：微软雅黑 → 黑体），unicode_minus 修复负号变方块
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHART_DIR = PROJECT_ROOT / "output" / "charts"

# 统一配色（蓝=主色，红=异常，绿=良好，橙=警示）
BLUE, RED, GREEN, ORANGE = "#2E86AB", "#E45756", "#54A24B", "#F58518"


def chart_daily_trend(daily):
    """每日单量趋势 + 7日滚动均线，返回 fig"""
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(daily.index, daily.values, color=BLUE, alpha=0.4, label="每日单量")
    ax.plot(daily.index, daily.rolling(7).mean(), color=RED, linewidth=2, label="7日均值")
    ax.set_title("每日订单量趋势（近90天）")
    ax.set_xlabel("日期")
    ax.set_ylabel("订单数")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def chart_carrier_time(carrier):
    """各承运商平均配送时长（柱状图），返回 fig"""
    carrier = carrier.sort_values("平均配送时长(小时)")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(carrier["承运商"], carrier["平均配送时长(小时)"], color=BLUE)
    ax.set_title("各承运商平均配送时长（小时）")
    ax.set_ylabel("小时")
    ax.bar_label(bars, padding=2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


def chart_carrier_rate(carrier):
    """各承运商准时率 vs 异常率（分组柱状图），返回 fig"""
    fig, ax = plt.subplots(figsize=(10, 4.5))
    pos = range(len(carrier))
    width = 0.38
    ax.bar([p - width / 2 for p in pos], carrier["准时率(%)"], width, label="准时率(%)", color=GREEN)
    ax.bar([p + width / 2 for p in pos], carrier["异常率(%)"], width, label="异常率(%)", color=RED)
    ax.set_xticks(list(pos))
    ax.set_xticklabels(carrier["承运商"])
    ax.set_ylabel("百分比(%)")
    ax.set_title("各承运商准时率 vs 异常率")
    ax.set_ylim(0, 110)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


def chart_exception_pie(exception):
    """异常类型占比（饼图），返回 fig"""
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = [ORANGE, RED, GREEN, "#9D7CB3"]
    ax.pie(exception.values, labels=exception.index, autopct="%1.1f%%",
           colors=colors, startangle=90, textprops={"fontsize": 12})
    ax.set_title("异常订单类型分布")
    fig.tight_layout()
    return fig


def chart_region(region):
    """收货区域分布（横向条形图），返回 fig"""
    region = region.sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(region.index, region.values, color=GREEN)
    ax.bar_label(bars, padding=2)
    ax.set_title("收货区域订单分布")
    ax.set_xlabel("订单数")
    ax.set_xlim(0, region.max() * 1.15)
    fig.tight_layout()
    return fig


def chart_top_cities(top_cities):
    """收货城市 TOP10（横向条形图），返回 fig"""
    top_cities = top_cities.sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(top_cities.index, top_cities.values, color=BLUE)
    ax.bar_label(bars, padding=2)
    ax.set_title("收货城市 TOP10")
    ax.set_xlabel("订单数")
    ax.set_xlim(0, top_cities.max() * 1.15)
    fig.tight_layout()
    return fig


def generate_all_charts(results, chart_dir=CHART_DIR):
    """把所有图保存成 PNG（命令行用），返回 {名称: 路径}"""
    chart_dir = Path(chart_dir)
    chart_dir.mkdir(parents=True, exist_ok=True)

    tasks = {
        "daily_trend.png":   chart_daily_trend(results["daily"]),
        "carrier_time.png":  chart_carrier_time(results["carrier"]),
        "carrier_rate.png":  chart_carrier_rate(results["carrier"]),
        "exception_pie.png": chart_exception_pie(results["exception"]),
        "region_bar.png":    chart_region(results["region"]),
        "top_cities.png":    chart_top_cities(results["top_cities"]),
    }

    paths = {}
    for filename, fig in tasks.items():
        p = chart_dir / filename
        fig.savefig(p, dpi=150)
        plt.close(fig)
        paths[filename] = p
    return paths


def main():
    df, _ = load_and_clean()
    results = run_all_analysis(df)
    paths = generate_all_charts(results)

    print("=" * 50)
    print("图表全部生成完成！")
    for name, p in paths.items():
        print(f"  {name}  ->  {p}")
    print("=" * 50)


if __name__ == "__main__":
    main()
