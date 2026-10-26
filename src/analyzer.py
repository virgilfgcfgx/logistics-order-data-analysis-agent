# -*- coding: utf-8 -*-
"""
阶段3：指标计算引擎
作用：基于清洗后的订单数据，自动算出总体概览、时效、准时率、成本、
     承运商对比、地区分布、单量趋势等所有核心指标。
运行：在项目根目录的终端执行  python src/analyzer.py

说明：本模块只负责"算"，每个函数返回一个明确的结果，
     后面的图表、大模型、网页都直接调用这些函数。
"""

from pathlib import Path

import pandas as pd

from data_loader import load_and_clean


# ----------------------------------------------------------------------
# 一、总体概览：把最关键的数字汇总成一个字典
# ----------------------------------------------------------------------
def overall_summary(df):
    total = len(df)
    signed = df["订单状态"].eq("已签收")
    in_transit = df["订单状态"].isin(["运输中", "已揽收"])
    exception = df["异常类型"].ne("无")

    # 准时：已签收，且实际配送时长 <= 承诺时效
    on_time = signed & df["配送时长(小时)"].le(df["承诺时效(小时)"])

    return {
        "总订单数": int(total),
        "已签收订单数": int(signed.sum()),
        "在途订单数": int(in_transit.sum()),
        "异常状态订单数": int(df["订单状态"].eq("异常").sum()),
        "签收率(%)": round(signed.sum() / total * 100, 1),
        "准时率(%)": round(on_time.sum() / signed.sum() * 100, 1),
        "异常订单数": int(exception.sum()),
        "异常率(%)": round(exception.sum() / total * 100, 1),
        "平均配送时长(小时)": round(df.loc[signed, "配送时长(小时)"].mean(), 1),
        "平均运费(元)": round(df["运费(元)"].mean(), 2),
        "总运费(元)": round(df["运费(元)"].sum(), 2),
    }


# ----------------------------------------------------------------------
# 二、各承运商综合表现对比
# ----------------------------------------------------------------------
def carrier_performance(df):
    d = df.copy()
    # 先加几列 0/1 标记，再用 groupby 聚合，比逐组 apply 更快也更稳
    d["_signed"] = d["订单状态"].eq("已签收").astype(int)
    d["_ontime"] = (
        d["订单状态"].eq("已签收")
        & d["配送时长(小时)"].le(d["承诺时效(小时)"])
    ).astype(int)
    d["_exception"] = d["异常类型"].ne("无").astype(int)

    g = d.groupby("承运商")
    perf = pd.DataFrame({
        "订单数": g.size(),
        "签收数": g["_signed"].sum(),
        "准时数": g["_ontime"].sum(),
        "异常数": g["_exception"].sum(),
        "平均配送时长(小时)": g["配送时长(小时)"].mean().round(1),
        "平均运费(元)": g["运费(元)"].mean().round(2),
    })
    # 准时率 = 准时数 / 签收数；异常率 = 异常数 / 订单数
    perf["准时率(%)"] = (perf["准时数"] / perf["签收数"] * 100).round(1)
    perf["异常率(%)"] = (perf["异常数"] / perf["订单数"] * 100).round(1)

    perf = perf.reset_index()
    return perf[["承运商", "订单数", "平均配送时长(小时)", "准时率(%)", "异常率(%)", "平均运费(元)"]]


# ----------------------------------------------------------------------
# 三、异常类型分布
# ----------------------------------------------------------------------
def exception_analysis(df):
    exc = df[df["异常类型"].ne("无")]
    return exc["异常类型"].value_counts()


# ----------------------------------------------------------------------
# 四、收货区域分布
# ----------------------------------------------------------------------
def region_analysis(df):
    return df["收货区域"].value_counts()


# ----------------------------------------------------------------------
# 五、收货城市 TOP10
# ----------------------------------------------------------------------
def top_cities(df, n=10):
    counts = df["收货城市"].value_counts()
    return counts.drop(labels=["未知"], errors="ignore").head(n)


# ----------------------------------------------------------------------
# 六、每日单量趋势（resample 会把没有订单的日期补成 0，折线更连续）
# ----------------------------------------------------------------------
def daily_trend(df):
    daily = df.set_index("下单时间").resample("D").size()
    daily.name = "订单数"
    return daily


# ----------------------------------------------------------------------
# 七、异常订单识别（规则引擎）：不依赖现成标签，逐单按业务规则判定
# ----------------------------------------------------------------------
def detect_exceptions(df):
    """按业务规则逐单识别异常，返回异常订单明细 DataFrame（含判定原因）"""
    d = df.copy()
    now_ref = d["下单时间"].max()  # 以数据中最新下单时间作为"当前参考时间"

    reasons = []
    over_hours = []

    for _, row in d.iterrows():
        r = []
        over = None
        status = row["订单状态"]
        exc = row["异常类型"]
        dur = row["配送时长(小时)"]
        promise = row["承诺时效(小时)"]

        # 规则1：已签收，但实际时长超过承诺时效 → 超时
        if status == "已签收" and pd.notna(dur) and dur > promise:
            r.append("超时")
            over = round(dur - promise, 1)

        # 规则2：包裹破损（物理状态，需业务标注）
        if exc == "破损":
            r.append("破损")

        # 规则3：丢失 / 拒收（未正常签收）
        if exc in ("丢失", "拒收"):
            r.append(exc)

        # 规则4：在途但已超过承诺时效仍未签收 → 疑似滞留
        if status in ("运输中", "已揽收") and pd.notna(row["发货时间"]):
            elapsed_hours = (now_ref - row["发货时间"]).total_seconds() / 3600
            if elapsed_hours > promise:
                r.append("疑似滞留")

        reasons.append("、".join(r))
        over_hours.append(over)

    d["判定原因"] = reasons
    d["超时小时数"] = over_hours
    return d[d["判定原因"] != ""].copy()


def export_exceptions(exc_df, path=None):
    """把异常订单明细导出为 Excel"""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "output" / "reports" / "异常订单清单.xlsx"
    cols = ["订单号", "承运商", "发货城市", "收货城市", "收货区域",
            "下单时间", "订单状态", "配送时长(小时)", "承诺时效(小时)",
            "运费(元)", "异常类型", "判定原因", "超时小时数"]
    exc_df[cols].to_excel(path, index=False)
    return path


# ----------------------------------------------------------------------
# 汇总：一次性算出所有结果，供网页和大模型使用
# ----------------------------------------------------------------------
def run_all_analysis(df):
    return {
        "overall": overall_summary(df),
        "carrier": carrier_performance(df),
        "exception": exception_analysis(df),
        "exception_detail": detect_exceptions(df),
        "region": region_analysis(df),
        "top_cities": top_cities(df),
        "daily": daily_trend(df),
    }


def main():
    df, _ = load_and_clean()

    print("=" * 60)
    print("【一、总体概览】")
    for k, v in overall_summary(df).items():
        print(f"  {k}: {v}")

    print("=" * 60)
    print("【二、各承运商表现对比】")
    print(carrier_performance(df).to_string(index=False))

    print("=" * 60)
    print("【三、异常类型分布】")
    print(exception_analysis(df).to_string())

    print("=" * 60)
    print("【四、收货区域分布】")
    print(region_analysis(df).to_string())

    print("=" * 60)
    print("【五、收货城市 TOP10】")
    print(top_cities(df).to_string())

    print("=" * 60)
    print("【六、最近 10 天单量】")
    print(daily_trend(df).tail(10).to_string())

    print("=" * 60)
    print("【七、异常订单识别（规则引擎）】")
    exc_df = detect_exceptions(df)
    print(f"共识别异常订单：{len(exc_df)} 单")
    print(exc_df[["订单号", "承运商", "收货城市", "订单状态", "判定原因", "超时小时数"]].head(15).to_string(index=False))
    out_path = export_exceptions(exc_df)
    print(f"完整异常清单已导出：{out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
