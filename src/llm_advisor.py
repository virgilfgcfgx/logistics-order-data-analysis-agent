# -*- coding: utf-8 -*-
"""
大模型解读模块（DeepSeek）：流式输出 + 联网搜索（function calling）
作用：把 pandas 精确计算出的指标（事实）喂给大模型，
     让它像数据分析师一样写诊断报告、回答自然语言提问；
     问答时若需要外部信息（行业基准/政策/新闻等），可自动调用博查联网搜索。

两个关键设计：
1. 防幻觉：本公司的数字一律用 pandas 算好的事实，大模型只解读、不编数字；
2. 工具调用：问答先发一次"非流式"请求让模型判断要不要联网，
   需要搜索就执行 search_web、把结果塞回对话，再发一次"流式"请求逐字回答。
运行：python src/llm_advisor.py
"""

import os
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from search_client import search_web_for_llm, is_configured as search_is_configured

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")  # 从 .env 文件读取密钥

MODEL = "deepseek-flash"                          # 对应 DeepSeek V4.1 Flash
BASE_URL = "https://api.deepseek.com"            # DeepSeek 兼容 OpenAI 接口


def get_client():
    """初始化大模型客户端，并检查 API Key 是否已配置"""
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key.startswith("请") or api_key.startswith("sk-在这里"):
        raise RuntimeError(
            "未检测到有效的 DEEPSEEK_API_KEY！\n"
            "请打开项目根目录的 .env 文件，把 Key 填到等号后面再运行。"
        )
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def build_facts_text(results):
    """把前面算好的指标（DataFrame/字典）整理成大模型好读的纯文本事实"""
    o = results["overall"]
    lines = ["【总体指标】"]
    for k, v in o.items():
        lines.append(f"- {k}：{v}")

    lines.append("\n【各承运商表现】")
    lines.append(results["carrier"].to_string(index=False))

    lines.append("\n【异常类型分布】")
    lines.append(results["exception"].to_string())

    lines.append("\n【收货区域分布】")
    lines.append(results["region"].to_string())

    lines.append("\n【收货城市 TOP10】")
    lines.append(results["top_cities"].to_string())

    lines.append("\n【最近 10 天每日单量】")
    lines.append(results["daily"].tail(10).to_string())

    return "\n".join(lines)


# 系统提示词：规定大模型的角色、任务和"不许编数字"的红线
SYSTEM_PROMPT = (
    "你是一名资深物流运营数据分析专家，正在向物流公司管理者汇报。\n"
    "用户会给你一份系统从订单明细中精确计算出的真实指标数据。\n"
    "你必须：\n"
    "1. 严格基于给定的事实数据，绝不编造数据里没有的任何数字；\n"
    "2. 用通俗易懂的中文，结论明确、可执行；\n"
    "3. 引用数字时要和原始数据保持一致。\n"
    "当数据中没有相关信息时，明确回答『根据现有数据无法判断』，不要臆测。"
)


# 给大模型看的"搜索工具说明书"（function calling 的 tools 定义）
SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "当问题需要互联网上的外部信息时调用，例如：行业平均水平/行业基准、"
                "政策法规、国家标准、最新新闻、快递公司公告或价格政策、淡旺季趋势、"
                "专业术语解释等。"
                "凡是只涉及本公司订单数据的问题（如某承运商的异常率、准时率、运费、"
                "本公司的异常类型分布等），不要调用本工具，直接用给定数据回答。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "精炼的搜索关键词，例如：快递行业平均准时率 2026"
                    }
                },
                "required": ["query"],
            },
        },
    }
]


def _build_report_messages(results):
    """组装"生成分析报告"的对话消息（报告只用本地数据，不联网）"""
    facts = build_facts_text(results)
    user_prompt = (
        "以下是本期（约90天）物流订单的真实指标数据：\n\n"
        f"{facts}\n\n"
        "请据此生成一份结构化分析报告，包含：\n"
        "一、总体表现（用关键数字概括）；\n"
        "二、发现的主要问题；\n"
        "三、各承运商的对比与选择建议；\n"
        "四、异常订单（尤其超时）的处理建议；\n"
        "五、下一步可执行的行动清单。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _build_qa_messages(results, question, history=None, web_enabled=False):
    """组装"问答"的对话消息（可带历史，实现多轮）；web_enabled 时告知它可以联网"""
    facts = build_facts_text(results)
    web_rule = ""
    if web_enabled:
        web_rule = (
            "\n\n【联网规则】你可以调用 search_web 工具查询外部信息：\n"
            "- 问本公司订单的（各承运商异常率/准时率/运费、异常类型、区域分布等），"
            "一律只用上面的本期数据，不要联网；\n"
            "- 需要行业基准、政策法规、国家标准、新闻、快递公司最新动态等外部信息时，"
            "才调用 search_web；\n"
            "- 一旦引用了网络信息，在回答末尾用『参考来源』列出对应标题和链接，"
            "并明确区分哪些是本公司数据、哪些是外部信息。"
        )
    system_msg = (
        SYSTEM_PROMPT
        + "\n\n本期真实数据如下，请只依据这些数据回答：\n"
        + facts
        + web_rule
    )
    messages = [{"role": "system", "content": system_msg}]
    if history:
        messages.extend(history)  # 带入之前的对话，实现多轮
    messages.append({"role": "user", "content": question})
    return messages


def _create(messages, stream=False, tools=None, temperature=0.3):
    """统一的请求入口：可控制是否流式、是否挂工具；统一关闭思考模式"""
    client = get_client()
    kwargs = dict(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        stream=stream,
        extra_body={"thinking": {"type": "disabled"}},  # 关闭思考模式，首字更快
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def _chat_stream(messages, temperature=0.3):
    """【流式核心】逐段 yield 模型的正式回答（delta.content；忽略思考过程）"""
    stream = _create(messages, stream=True, temperature=temperature)
    for chunk in stream:
        if not chunk.choices:           # 末尾可能出现不带 choices 的统计包，跳过
            continue
        delta = chunk.choices[0].delta
        piece = getattr(delta, "content", None)
        if piece:
            yield piece


def _fake_stream(text, chunk_size=3):
    """把已得到的完整文本切成小段，模拟打字机效果（不联网时无需再发一次请求）"""
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


def plan_qa(results, question, history=None, on_event=None):
    """第一次请求：让模型判断是否需要联网；若需要则执行搜索。

    on_event(event, data)：可选回调，用于向界面汇报进度
        event="searching" 时 data 为搜索词；event="searched" 时 data 为来源列表。
    返回：
        {"need_stream": True,  "messages": 含搜索结果的消息, "sources": [...]}  → 再流式回答
        {"need_stream": False, "answer": 完整答案,          "sources": []}      → 直接展示
    """
    web_enabled = search_is_configured()  # 没配博查 Key 时自动降级为纯本地问答
    messages = _build_qa_messages(results, question, history, web_enabled=web_enabled)
    resp = _create(messages, stream=False, tools=(SEARCH_TOOLS if web_enabled else None))
    msg = resp.choices[0].message

    # 模型没有要求调用工具 → 用本地数据直接回答
    if not getattr(msg, "tool_calls", None):
        return {"need_stream": False, "answer": msg.content or "", "sources": []}

    # 模型要求联网：先把它的"工具调用请求"作为 assistant 消息加进对话
    messages.append(msg.model_dump(exclude_none=True))
    sources = []
    for tc in msg.tool_calls:
        if tc.function.name != "search_web":
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        query = args.get("query", question)
        if on_event:
            on_event("searching", query)
        try:
            tool_text, items = search_web_for_llm(query)
        except Exception as e:
            tool_text, items = f"（联网搜索失败：{e}）", []
        if on_event:
            on_event("searched", items)
        sources.extend(items)
        # 把搜索结果作为 tool 消息回传给模型
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": "search_web",
            "content": tool_text,
        })
    return {"need_stream": True, "messages": messages, "sources": sources}


def stream_answer(messages):
    """第二次请求：搜索完成后，结合结果流式逐字生成最终回答（不再挂工具）"""
    yield from _chat_stream(messages)


def generate_report_stream(results):
    """流式生成诊断报告（仅本地数据），逐段 yield"""
    yield from _chat_stream(_build_report_messages(results))


def ask_question_stream(results, question, history=None, on_event=None):
    """一体化流式问答（命令行/简单场景用）；网页建议直接用 plan_qa + stream_answer。"""
    plan = plan_qa(results, question, history, on_event=on_event)
    if plan["need_stream"]:
        yield from stream_answer(plan["messages"])
    else:
        yield from _fake_stream(plan["answer"])


def _chat(messages, temperature=0.3):
    """非流式：收集完整文本"""
    return "".join(_chat_stream(messages, temperature))


def generate_report(results):
    """非流式：返回完整分析报告"""
    return _chat(_build_report_messages(results))


def main():
    """命令行演示：一个需要外部信息的问题，展示 决策→搜索→流式回答 的全过程"""
    from data_loader import load_and_clean
    from analyzer import run_all_analysis

    df, _ = load_and_clean()
    results = run_all_analysis(df)

    question = "我们公司的准时率表现如何？快递行业的平均准时率大概是多少？"
    print("=" * 60)
    print("用户提问：", question)
    print("=" * 60)

    def on_event(event, data):
        if event == "searching":
            print(f"\n[联网] 正在搜索：{data}\n")
        elif event == "searched":
            print(f"[联网] 拿到 {len(data)} 条来源\n")

    plan = plan_qa(results, question, on_event=on_event)
    if plan["need_stream"]:
        print("-" * 60)
        for piece in stream_answer(plan["messages"]):
            print(piece, end="", flush=True)
        print("\n" + "=" * 60)
        print("参考来源：")
        for s in plan["sources"]:
            print("-", s["title"], s["url"])
    else:
        print(plan["answer"])


if __name__ == "__main__":
    main()
