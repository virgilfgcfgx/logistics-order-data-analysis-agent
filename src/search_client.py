# -*- coding: utf-8 -*-
"""
联网搜索模块（博查 Bocha Web Search API）
作用：当大模型判断需要外部信息（行业基准、政策、新闻等）时，由本模块真正去网上搜索，
     再把"标题 + 链接 + 摘要"整理成大模型好读的文本返回。

它和大模型是"分工"关系：
  - 大模型负责"决定要不要搜、搜什么词、怎么综合结果"；
  - 本模块负责"老老实实执行搜索"，自己不做任何主观判断。
需要在项目根目录 .env 里配置 BOCHA_API_KEY。
运行自测：python src/search_client.py   （需要先配好 Key）
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

BOCHA_URL = "https://api.bochaai.com/v1/web-search"


def _get_api_key():
    """读取博查 Key；未配置时返回空字符串"""
    return os.getenv("BOCHA_API_KEY", "").strip()


def is_configured():
    """是否已配置博查搜索 Key（供网页判断要不要开启联网功能）"""
    key = _get_api_key()
    return bool(key) and not key.startswith("请")


def bocha_search(query, count=6):
    """调用博查 Web Search，返回结构化结果列表。

    返回：[{title, url, snippet, site}, ...]
    任何异常（未配置 Key、网络失败、余额不足等）都返回空列表，由调用方降级处理。
    """
    key = _get_api_key()
    if not key or key.startswith("请"):
        raise RuntimeError(
            "未配置 BOCHA_API_KEY！\n"
            "请打开项目根目录 .env，填入博查 Key（BOCHA_API_KEY=sk-...）。"
        )

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "summary": True,            # 返回正文摘要，信息更全
        "freshness": "noLimit",     # 不限制时间
        "count": count,             # 返回条数
    }
    resp = requests.post(BOCHA_URL, headers=headers, json=payload, timeout=20)
    if resp.status_code == 401:
        raise RuntimeError("博查 Key 无效（401），请检查 .env 里的 BOCHA_API_KEY。")
    if resp.status_code == 403:
        raise RuntimeError("博查账户余额不足或未开通（403），请到开放平台订阅免费试用/充值。")
    if resp.status_code == 429:
        raise RuntimeError("博查请求过于频繁（429），请稍后再试。")
    resp.raise_for_status()

    data = resp.json()
    # 博查返回结构兼容 Bing：data.webPages.value 是网页结果数组
    web_pages = ((data.get("data") or {}).get("webPages") or {})
    raw_items = web_pages.get("value", []) or []

    items = []
    for it in raw_items[:count]:
        items.append({
            "title": it.get("name", "") or "",
            "url": it.get("url", "") or "",
            "snippet": it.get("summary") or it.get("snippet") or "",
            "site": it.get("siteName", "") or "",
        })
    return items


def search_web_for_llm(query, count=6):
    """执行搜索并把结果拼成大模型好读的文本。

    返回：(给大模型的文本, 来源列表)
    """
    items = bocha_search(query, count=count)
    if not items:
        return "（联网搜索没有返回结果，请基于已有数据谨慎回答）", []

    blocks = [f"以下是关于「{query}」的联网搜索结果，请据此回答，并在回答末尾列出参考来源："]
    for i, it in enumerate(items, 1):
        blocks.append(
            f"[{i}] 标题：{it['title']}\n"
            f"    来源：{it['site']}  链接：{it['url']}\n"
            f"    摘要：{it['snippet']}"
        )
    return "\n".join(blocks), items


def main():
    if not is_configured():
        print("尚未配置 BOCHA_API_KEY，请先在 .env 中填写。")
        return
    q = "快递行业平均准时率 行业标准"
    print(f"正在联网搜索：{q}")
    text, items = search_web_for_llm(q)
    print(f"共拿到 {len(items)} 条结果：\n")
    for it in items:
        print("-", it["title"], "|", it["site"])
        print(" ", it["url"])
        print(" ", it["snippet"][:100].replace("\n", " "))
        print()


if __name__ == "__main__":
    main()
