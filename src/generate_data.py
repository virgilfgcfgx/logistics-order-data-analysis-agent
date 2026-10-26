# -*- coding: utf-8 -*-
"""
阶段1：生成模拟物流订单数据
作用：生成 1000 单贴近真实的物流订单，保存为 Excel，供后续分析使用。
运行：在项目根目录的终端执行  python src/generate_data.py
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# 固定随机种子，保证每次生成的数据一致，方便教学复现（想看不同数据可以改这行或删掉）
random.seed(42)

# 项目根目录（本文件在 src/ 下，所以向上两级）。这样无论从哪里运行都能找到正确路径。
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------
# 1. 承运商配置：不同快递公司在「时效、价格、异常率、承诺时效」上的差异
#    把业务规律集中写在一个字典里，后面想调整某家快递的表现，只改这里即可。
# ----------------------------------------------------------------------
CARRIERS = {
    "顺丰速运": {"base_hours": 24, "base_fee": 15, "price_per_kg": 12.0, "exception_rate": 0.02,  "promise_hours": 48},
    "京东物流": {"base_hours": 28, "base_fee": 13, "price_per_kg": 10.0, "exception_rate": 0.025, "promise_hours": 48},
    "中通快递": {"base_hours": 48, "base_fee": 8,  "price_per_kg": 6.0,  "exception_rate": 0.05,  "promise_hours": 72},
    "圆通速递": {"base_hours": 50, "base_fee": 8,  "price_per_kg": 5.5,  "exception_rate": 0.055, "promise_hours": 72},
    "韵达快递": {"base_hours": 52, "base_fee": 7,  "price_per_kg": 5.0,  "exception_rate": 0.06,  "promise_hours": 72},
    "申通快递": {"base_hours": 50, "base_fee": 7,  "price_per_kg": 5.5,  "exception_rate": 0.058, "promise_hours": 72},
    "邮政EMS":  {"base_hours": 60, "base_fee": 10, "price_per_kg": 7.0,  "exception_rate": 0.04,  "promise_hours": 96},
}
# 承运商被选中的概率（模拟市场份额，顺丰/京东/中通占比较高）
CARRIER_WEIGHTS = [0.20, 0.18, 0.18, 0.14, 0.13, 0.10, 0.07]

# ----------------------------------------------------------------------
# 2. 城市配置
# ----------------------------------------------------------------------
# 发货城市：商品通常从少数几个大仓发出，用加权让广州/深圳/义乌/上海更多
SENDER_CITIES = ["广州", "深圳", "上海", "义乌", "杭州", "北京", "武汉", "成都"]
SENDER_WEIGHTS = [0.22, 0.20, 0.16, 0.14, 0.10, 0.08, 0.05, 0.05]

# 收货城市：分散到全国各地
RECEIVER_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "武汉", "西安", "杭州", "南京", "重庆",
    "天津", "苏州", "长沙", "郑州", "青岛", "济南", "合肥", "福州", "厦门", "昆明",
    "贵阳", "南宁", "海口", "南昌", "太原", "石家庄", "沈阳", "大连", "长春", "哈尔滨",
    "兰州", "乌鲁木齐", "江门", "东莞", "佛山", "宁波", "无锡", "温州",
]

# 收货城市 -> 所在区域（用于后面的地区分布分析）
CITY_REGION = {
    "北京": "华北", "天津": "华北", "石家庄": "华北", "太原": "华北",
    "上海": "华东", "南京": "华东", "杭州": "华东", "苏州": "华东", "宁波": "华东",
    "无锡": "华东", "温州": "华东", "合肥": "华东", "福州": "华东", "厦门": "华东",
    "南昌": "华东", "义乌": "华东", "青岛": "华东", "济南": "华东",
    "广州": "华南", "深圳": "华南", "江门": "华南", "东莞": "华南", "佛山": "华南",
    "南宁": "华南", "海口": "华南",
    "武汉": "华中", "长沙": "华中", "郑州": "华中",
    "成都": "西南", "重庆": "西南", "昆明": "西南", "贵阳": "西南",
    "西安": "西北", "兰州": "西北", "乌鲁木齐": "西北",
    "沈阳": "东北", "大连": "东北", "长春": "东北", "哈尔滨": "东北",
}

# ----------------------------------------------------------------------
# 3. 异常类型与权重
# ----------------------------------------------------------------------
EXCEPTION_TYPES = ["超时", "破损", "丢失", "拒收"]
EXCEPTION_WEIGHTS = [0.40, 0.25, 0.15, 0.20]

# ----------------------------------------------------------------------
# 4. 时间范围：生成「最近 90 天」的订单
# ----------------------------------------------------------------------
END_DATE = datetime(2026, 10, 23, 23, 0, 0)
START_DATE = END_DATE - timedelta(days=90)

N_ORDERS = 2000  # 生成订单总数


def random_datetime(start, end):
    """在两个时间之间随机取一个时刻，并让白天(9~21点)下单更多（符合真实下单习惯）"""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    dt = start + timedelta(seconds=random_seconds)
    if random.random() < 0.7:  # 70% 概率把时刻挪到白天
        dt = dt.replace(hour=random.randint(9, 21), minute=random.randint(0, 59))
    return dt


def generate_one_order(index):
    """生成一单完整数据并返回字典"""
    carrier = random.choices(list(CARRIERS.keys()), weights=CARRIER_WEIGHTS, k=1)[0]
    cfg = CARRIERS[carrier]

    sender = random.choices(SENDER_CITIES, weights=SENDER_WEIGHTS, k=1)[0]
    receiver = random.choice(RECEIVER_CITIES)
    region = CITY_REGION.get(receiver, "其他")

    order_time = random_datetime(START_DATE, END_DATE)

    # 揽收时长（下单->发货）：顺丰/京东更快
    if carrier in ("顺丰速运", "京东物流"):
        pickup_hours = random.uniform(2, 6)
    else:
        pickup_hours = random.uniform(4, 14)
    ship_time = order_time + timedelta(hours=pickup_hours)

    # 重量：用随机数的平方，让小重量订单更集中（大部分包裹偏轻）
    weight = round(0.1 + (random.random() ** 2) * 15, 2)
    # 运费 = 起步价 + 续重单价 × 重量，加少量随机浮动
    fee = cfg["base_fee"] + cfg["price_per_kg"] * weight + random.uniform(-1, 1)
    fee = round(fee, 2)

    # 干线运输时长（发货->签收），基础时长 + 随机波动
    transport_hours = cfg["base_hours"] + random.uniform(-6, 18)

    # 判断是否异常
    is_exception = random.random() < cfg["exception_rate"]
    exception_type = "无"
    status = "已签收"
    delivery_time = None
    delivery_hours = None

    if is_exception:
        exception_type = random.choices(EXCEPTION_TYPES, weights=EXCEPTION_WEIGHTS, k=1)[0]
        if exception_type == "超时":
            # 超时：最终仍签收，但比承诺时间慢
            transport_hours = cfg["promise_hours"] + random.uniform(6, 48)
            status = "已签收"
            delivery_time = ship_time + timedelta(hours=transport_hours)
        elif exception_type == "破损":
            # 破损：货送到了但有破损
            status = "已签收"
            delivery_time = ship_time + timedelta(hours=transport_hours)
        else:  # 丢失 / 拒收：没有正常签收
            status = "异常"
            delivery_time = None
    else:
        # 正常订单：若预计签收时间晚于数据截止日，说明还在路上
        estimated_delivery = ship_time + timedelta(hours=transport_hours)
        if estimated_delivery > END_DATE:
            status = random.choice(["已揽收", "运输中"])
            delivery_time = None
        else:
            status = "已签收"
            delivery_time = estimated_delivery

    # 实际配送时长（仅对已签收订单可算）
    if delivery_time is not None:
        delivery_hours = round((delivery_time - ship_time).total_seconds() / 3600, 1)

    # 订单号：承运商简写 + 日期 + 4 位序号
    prefix = {
        "顺丰速运": "SF", "京东物流": "JD", "中通快递": "ZT", "圆通速递": "YT",
        "韵达快递": "YD", "申通快递": "ST", "邮政EMS": "EMS",
    }[carrier]
    order_id = f"{prefix}{order_time.strftime('%Y%m%d')}{index:04d}"

    return {
        "订单号": order_id,
        "承运商": carrier,
        "发货城市": sender,
        "收货城市": receiver,
        "收货区域": region,
        "下单时间": order_time,
        "发货时间": ship_time,
        "签收时间": delivery_time,
        "配送时长(小时)": delivery_hours,
        "承诺时效(小时)": cfg["promise_hours"],
        "重量(kg)": weight,
        "运费(元)": fee,
        "订单状态": status,
        "异常类型": exception_type,
    }


def main():
    rows = [generate_one_order(i + 1) for i in range(N_ORDERS)]
    df = pd.DataFrame(rows)

    # ---- 故意混入脏数据，供阶段2清洗演示 ----
    dup = df.sample(5, random_state=1)                                  # 复制5行，制造重复
    df.loc[df.sample(8, random_state=2).index, "运费(元)"] = None       # 8行运费缺失
    df.loc[df.sample(8, random_state=3).index, "收货城市"] = None       # 8行收货城市缺失
    bad_idx = df.sample(5, random_state=4).index                       # 5行下单时间格式不一致
    df.loc[bad_idx, "下单时间"] = df.loc[bad_idx, "下单时间"].apply(
        lambda x: x.strftime("%Y/%m/%d %H:%M") if pd.notna(x) else x
    )
    df = pd.concat([df, dup], ignore_index=True)

    out_path = PROJECT_ROOT / "data" / "raw" / "logistics_orders.xlsx"
    df.to_excel(out_path, index=False)

    print("=" * 50)
    print("模拟物流订单数据生成完成！")
    print(f"文件路径：{out_path}")
    print(f"总行数（含重复）：{len(df)}")
    print("-" * 50)
    print("各承运商订单数：")
    print(df["承运商"].value_counts().to_string())
    print("-" * 50)
    print("各订单状态数量：")
    print(df["订单状态"].value_counts().to_string())
    print("-" * 50)
    print("各异常类型数量：")
    print(df["异常类型"].value_counts().to_string())
    print("=" * 50)


if __name__ == "__main__":
    main()
