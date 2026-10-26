# -*- coding: utf-8 -*-
"""
阶段2：数据读取与清洗
作用：读取原始 Excel，把重复、缺失、格式混乱的数据清洗干净，输出干净的 DataFrame。
     后面的分析、图表、网页都调用这个模块来获取干净数据。
运行：在项目根目录的终端执行  python src/data_loader.py
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "logistics_orders.xlsx"


def load_raw_data(path=DEFAULT_DATA_PATH):
    """读取原始 Excel，不做任何处理"""
    df = pd.read_excel(path)
    return df


def clean_data(df):
    """执行清洗，返回 (干净的 DataFrame, 清洗动作记录)"""
    df = df.copy()          # 复制一份，避免清洗过程改动到原始数据
    report = {}             # 记录每一步处理了多少条，方便对比

    # ---- 1. 统一日期格式 ----
    # 原始"下单时间"里混着 datetime 和 "2026/10/01 12:30" 这种字符串，
    # errors="coerce" 表示无法解析的变成空时间(NaT)，而不是报错
    for col in ["下单时间", "发货时间", "签收时间"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # ---- 2. 去除重复订单（按订单号去重，保留第一条）----
    before = len(df)
    df = df.drop_duplicates(subset=["订单号"], keep="first")
    report["删除重复订单"] = before - len(df)

    # ---- 3. 填充缺失运费 ----
    # 用"同一承运商"的运费中位数来补，比用全公司平均值更合理
    # （顺丰本身就贵，用中通的均价去补顺丰显然不合理）
    missing_fee = int(df["运费(元)"].isna().sum())
    df["运费(元)"] = df.groupby("承运商")["运费(元)"].transform(
        lambda s: s.fillna(s.median())
    )
    df["运费(元)"] = df["运费(元)"].fillna(df["运费(元)"].median())  # 兜底
    report["填充缺失运费"] = missing_fee

    # ---- 4. 填充缺失收货城市 ----
    missing_city = int(df["收货城市"].isna().sum())
    df["收货城市"] = df["收货城市"].fillna("未知")
    report["填充缺失收货城市"] = missing_city

    # ---- 5. 重置行号 ----
    df = df.reset_index(drop=True)
    return df, report


def load_and_clean(path=DEFAULT_DATA_PATH):
    """一步到位：读取 + 清洗，供其他模块直接调用"""
    raw = load_raw_data(path)
    clean, report = clean_data(raw)
    return clean, report


def main():
    raw = load_raw_data()
    print("=" * 60)
    print("【清洗前】")
    print(f"总行数：{len(raw)}")
    print("各列缺失值数量：")
    print(raw.isna().sum().to_string())
    print(f"重复订单号数量：{raw['订单号'].duplicated().sum()}")

    clean, report = clean_data(raw)

    print("=" * 60)
    print("【清洗动作】")
    for action, count in report.items():
        print(f"  {action}：{count} 条")

    print("=" * 60)
    print("【清洗后】")
    print(f"总行数：{len(clean)}")
    print("各列缺失值数量：")
    print(clean.isna().sum().to_string())
    print(f"重复订单号数量：{clean['订单号'].duplicated().sum()}")
    print("-" * 60)
    print("前 5 行预览：")
    print(clean.head().to_string())
    print("=" * 60)


if __name__ == "__main__":
    main()
