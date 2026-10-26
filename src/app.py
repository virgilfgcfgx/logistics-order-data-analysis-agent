# -*- coding: utf-8 -*-
"""
阶段7：Streamlit 网页界面（物流订单数据自动分析 Agent 的最终入口）
功能：
  1. 上传 Excel（或一键加载示例数据）
  2. 自动清洗、计算指标、识别异常
  3. 指标卡片 + 6 张可视化图表
  4. 承运商对比表 + 异常订单清单（可下载）
  5. 一键生成 AI 分析报告
  6. 与 AI 自然语言对话提问
运行：在项目根目录的终端执行  streamlit run src/app.py
"""

import io

import pandas as pd
import streamlit as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data_loader import load_and_clean, clean_data
from analyzer import run_all_analysis, detect_exceptions
from charts import (
    chart_daily_trend, chart_carrier_time, chart_carrier_rate,
    chart_exception_pie, chart_region, chart_top_cities,
)
from llm_advisor import (
    generate_report_stream, plan_qa, stream_answer, _fake_stream,
)
from search_client import is_configured as search_configured

# 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

st.set_page_config(page_title="物流订单数据分析 Agent", layout="wide")
st.title("物流订单数据自动分析 Agent")
st.caption("自动清洗 · 指标计算 · 异常识别 · 可视化 · AI 解读与问答")

# ----------------------------------------------------------------------
# 初始化会话状态（Streamlit 每次交互都会重跑脚本，用它来"记住"数据）
# ----------------------------------------------------------------------
if "df" not in st.session_state:
    st.session_state.df = None
    st.session_state.results = None
    st.session_state.clean_info = None
    st.session_state.ai_report = None
    st.session_state.chat_history = []
    st.session_state.loaded_source = None

# ----------------------------------------------------------------------
# 侧边栏：选择数据
# ----------------------------------------------------------------------
st.sidebar.header("① 选择数据")
demo_clicked = st.sidebar.button("加载示例数据（1000 单）")
uploaded = st.sidebar.file_uploader("或上传物流订单 Excel", type=["xlsx", "xls"])

# 计算当前数据源的唯一标识（避免每次交互都重复分析）
current_source = None
if demo_clicked:
    current_source = "demo"
elif uploaded is not None:
    current_source = f"upload:{uploaded.name}:{uploaded.size}"

if current_source is not None and st.session_state.loaded_source != current_source:
    with st.spinner("正在读取、清洗并分析数据 ..."):
        try:
            if current_source == "demo":
                df, clean_info = load_and_clean()
            else:
                raw = pd.read_excel(uploaded)
                df, clean_info = clean_data(raw)
            st.session_state.df = df
            st.session_state.results = run_all_analysis(df)
            st.session_state.clean_info = clean_info
            st.session_state.ai_report = None
            st.session_state.chat_history = []
            st.session_state.loaded_source = current_source
        except Exception as e:
            st.sidebar.error(f"数据处理失败：{e}")

# 没有数据时，显示引导并停止
if st.session_state.df is None:
    st.info("请在左侧上传物流订单 Excel，或点击「加载示例数据」开始体验。")
    st.stop()

# 数据已就绪
df = st.session_state.df
results = st.session_state.results
overall = results["overall"]

# 侧边栏展示清洗结果
with st.sidebar:
    st.divider()
    st.header("② 清洗结果")
    if st.session_state.clean_info:
        for k, v in st.session_state.clean_info.items():
            st.write(f"{k}：{v} 条")
    st.write(f"有效订单：{len(df)} 单")

# ----------------------------------------------------------------------
# 核心指标卡片
# ----------------------------------------------------------------------
st.subheader("核心指标看板")
c1, c2, c3, c4 = st.columns(4)
c1.metric("总订单数", overall["总订单数"])
c2.metric("签收率", f"{overall['签收率(%)']}%")
c3.metric("准时率", f"{overall['准时率(%)']}%")
c4.metric("异常率", f"{overall['异常率(%)']}%")

c5, c6, c7, c8 = st.columns(4)
c5.metric("平均配送时长", f"{overall['平均配送时长(小时)']} h")
c6.metric("平均运费", f"{overall['平均运费(元)']} 元")
c7.metric("在途订单", overall["在途订单数"])
c8.metric("总运费", f"{overall['总运费(元)']} 元")

st.divider()

# ----------------------------------------------------------------------
# 分 Tab 展示：图表 / 承运商与异常 / AI报告 / AI问答
# ----------------------------------------------------------------------
tab_chart, tab_data, tab_report, tab_chat = st.tabs(
    ["可视化图表", "承运商与异常", "AI 分析报告", "AI 问答"]
)

# ---------- Tab1：图表 ----------
with tab_chart:
    st.pyplot(chart_daily_trend(results["daily"]), use_container_width=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.pyplot(chart_carrier_time(results["carrier"]), use_container_width=True)
    with col_b:
        st.pyplot(chart_carrier_rate(results["carrier"]), use_container_width=True)
    col_c, col_d = st.columns(2)
    with col_c:
        st.pyplot(chart_exception_pie(results["exception"]), use_container_width=True)
    with col_d:
        st.pyplot(chart_region(results["region"]), use_container_width=True)
    st.pyplot(chart_top_cities(results["top_cities"]), use_container_width=True)

# ---------- Tab2：承运商对比 + 异常清单 ----------
with tab_data:
    st.subheader("各承运商表现对比")
    st.dataframe(results["carrier"], use_container_width=True, hide_index=True)

    st.subheader("异常订单明细（规则引擎自动识别）")
    exc_df = detect_exceptions(df)
    st.write(f"共识别异常订单 **{len(exc_df)} 单**")
    exc_cols = ["订单号", "承运商", "发货城市", "收货城市", "收货区域",
                "下单时间", "订单状态", "配送时长(小时)", "承诺时效(小时)",
                "运费(元)", "异常类型", "判定原因", "超时小时数"]
    st.dataframe(exc_df[exc_cols], use_container_width=True, hide_index=True)

    buffer = io.BytesIO()
    exc_df[exc_cols].to_excel(buffer, index=False)
    st.download_button(
        "下载异常订单清单.xlsx",
        buffer.getvalue(),
        file_name="异常订单清单.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ---------- Tab3：AI 分析报告（流式）----------
with tab_report:
    st.subheader("AI 分析报告（基于真实计算结果，不编造数据）")
    if st.button("生成 AI 分析报告", type="primary"):
        st.caption("正在生成，内容会逐字出现 ...")
        try:
            # st.write_stream 边接收片段边渲染（打字机效果），返回值是完整文本
            st.session_state.ai_report = st.write_stream(generate_report_stream(results))
        except Exception as e:
            st.error(f"调用大模型失败：{e}")
    elif st.session_state.ai_report:
        # 生成完成后，之后页面重跑时用完整 Markdown 展示
        st.markdown(st.session_state.ai_report)

# ---------- Tab4：AI 问答（可联网）----------
with tab_chat:
    st.subheader("向数据分析师提问")
    st.caption("例如：哪家快递最值得用？为什么超时这么多？能给我降本建议吗？")
    # 提示联网能力是否已开启
    if search_configured():
        st.caption("🟢 已开启联网：问到行业基准、政策、新闻等外部信息时会自动联网搜索")
    else:
        st.caption("⚪ 未配置联网搜索（.env 里没有 BOCHA_API_KEY）：当前仅回答本公司数据问题")

    # 先渲染历史对话
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("请输入你的问题 ...")
    if question:
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            sources = []
            try:
                # 第一阶段：模型判断是否联网，并执行搜索（非流式，用状态条展示进度）
                with st.status("正在分析 ...", expanded=False) as status:
                    def on_event(event, data):
                        if event == "searching":
                            status.update(label=f"🌐 正在联网搜索：{data}")
                            st.write(f"搜索关键词：{data}")
                        elif event == "searched":
                            sources.extend(data)
                            status.update(label=f"已获取 {len(data)} 条网络结果，正在撰写回答 ...")

                    plan = plan_qa(
                        results, question,
                        st.session_state.chat_history[:-1],  # 传入此前的历史
                        on_event=on_event,
                    )

                # 第二阶段：流式逐字渲染最终答案
                if plan["need_stream"]:
                    answer = st.write_stream(stream_answer(plan["messages"]))
                else:
                    answer = st.write_stream(_fake_stream(plan["answer"]))
                answer = answer or ""

                # 可折叠展示联网参考来源
                if plan["sources"]:
                    with st.expander(f"🌐 联网参考来源（{len(plan['sources'])} 条）"):
                        for s in plan["sources"]:
                            st.markdown(f"- [{s['title']}]({s['url']})")
            except Exception as e:
                answer = f"调用大模型失败：{e}"
                st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
