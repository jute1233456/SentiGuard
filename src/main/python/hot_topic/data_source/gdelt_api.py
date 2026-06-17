import requests
import time
from datetime import datetime

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def fetch_gdelt_news(query, timespan="1d", max_retries=3):
    """
    获取24小时内GDELT新闻（只取标题、时间、链接）
    """

    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "timespan": timespan,
        "sort": "datedesc"
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(BASE_URL, params=params, timeout=10)

            # 处理限流
            if response.status_code == 429:
                print("429限流，等待5秒重试...")
                time.sleep(5)
                continue

            response.raise_for_status()
            data = response.json()

            articles = data.get("articles", [])

            results = []
            for a in articles:
                results.append({
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "source": a.get("sourceCountry") or a.get("domain"),
                    "time": a.get("seendate")
                })

            return results

        except Exception as e:
            print(f"请求失败，第{attempt+1}次重试:", e)
            time.sleep(3)

    return []


def fetch_multi_queries(query_list):
    """
    多关键词批量获取新闻
    """
    all_news = []

    for q in query_list:
        print(f"正在获取: {q}")

        news = fetch_gdelt_news(q)

        for n in news:
            n["query"] = q  # 标记来源关键词
            all_news.append(n)

        time.sleep(3)  # ⭐防止429关键点

    return all_news


if __name__ == "__main__":

    queries = [
        "artificial intelligence",
        "climate change",
        "economy",
        "war",
        "technology"
    ]

    news_data = fetch_multi_queries(queries)

    print("\n===== 获取结果 =====")
    print(f"总新闻数: {len(news_data)}")

    for i, n in enumerate(news_data[:10]):
        print(f"\n[{i+1}] {n['title']}")
        print(f"时间: {n['time']}")
        print(f"来源: {n['source']}")
        print(f"链接: {n['url']}")