"""
线香每日资讯摘要脚本
流程：抓 RSS + 搜狗公众号关键词 → 去重 → LLM 分类摘要 → 发飞书会话
"""
import os
import re
import sys
import yaml
import feedparser
import requests
import random
import time
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from urllib.parse import quote

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

SOGOU_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_feeds(cfg):
    """抓所有 RSS 源，返回文章列表"""
    hours_back = cfg["fetch"]["hours_back"]
    max_per_feed = cfg["fetch"]["max_articles_per_feed"]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    articles = []
    seen_links = set()

    for feed in cfg["feeds"]:
        if not feed.get("enabled", True):
            print(f"[SKIP] {feed['name']} (已禁用)", file=sys.stderr)
            continue
        try:
            resp = requests.get(feed["url"], timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            parsed = feedparser.parse(resp.content)
            count = 0
            for entry in parsed.entries:
                link = entry.get("link", "")
                if not link or link in seen_links:
                    continue
                # 时间过滤
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                seen_links.add(link)
                articles.append({
                    "source": feed["name"],
                    "title": entry.get("title", "").strip(),
                    "link": link,
                    "summary": entry.get("summary", "").strip()[:300],
                })
                count += 1
                if count >= max_per_feed:
                    break
            print(f"[OK] {feed['name']}: {count} 条", file=sys.stderr)
        except Exception as e:
            print(f"[FAIL] {feed['name']}: {e}", file=sys.stderr)

    return articles


def fetch_sogou_wechat(cfg):
    """搜狗微信搜索：按关键词检索公众号文章（无需公众号名单）
    返回文章列表；低频抓取 + 随机延时，降低风控概率
    """
    sg = cfg.get("sogou", {})
    keywords = sg.get("keywords", [])
    max_per = sg.get("max_articles_per_keyword", 6)
    if not keywords:
        return []

    articles = []
    seen_links = set()
    base = "https://weixin.sogou.com"

    for kw in keywords:
        try:
            url = f"{base}/weixin?type=2&query=" + quote(kw)
            resp = requests.get(url, timeout=12, headers=SOGOU_HEADERS)
            text = resp.text

            if "验证码" in text or "antispider" in text or "请输入验证码" in text:
                print(f"[WARN] 搜狗触发风控（关键词：{kw}），今日跳过该词", file=sys.stderr)
                continue

            # 标题 + 跳转链接：<h3><a href="/link?url=...">标题</a></h3>
            items = re.findall(
                r'<h3>\s*<a[^>]+href="(/link\?url=[^"]+)"[^>]*>(.*?)</a>\s*</h3>', text, re.S)
            # 摘要：<p class="txt-info" ...>摘要</p>
            summaries = re.findall(r'<p class="txt-info"[^>]*>(.*?)</p>', text, re.S)

            count = 0
            for idx, (href, title_html) in enumerate(items):
                if count >= max_per:
                    break
                title = re.sub(r'<[^>]+>', '', title_html).strip()
                summary = re.sub(r'<[^>]+>', '', summaries[idx]).strip() if idx < len(summaries) else ""
                link = base + href.split('&amp;')[0]
                if not title or link in seen_links:
                    continue
                seen_links.add(link)
                articles.append({
                    "source": f"公众号·{kw}",
                    "title": title,
                    "link": link,
                    "summary": summary[:200],
                })
                count += 1
            print(f"[OK] 公众号·{kw}: {count} 条", file=sys.stderr)

            # 随机延时，降低搜狗风控概率
            time.sleep(random.uniform(3, 7))
        except Exception as e:
            print(f"[FAIL] 公众号·{kw}: {e}", file=sys.stderr)

    return articles


def build_prompt(articles, cfg):
    """构造 LLM prompt"""
    today = datetime.now().strftime("%Y-%m-%d")
    cats = "、".join(cfg["categories"])

    articles_text = "\n\n".join(
        [f"【{a['source']}】{a['title']}\n{a['link']}\n{a['summary']}" for a in articles]
    )

    return f"""你是一个线香行业的资深编辑。今天是 {today}。

以下是过去 24 小时从各 RSS 源抓到的线香相关资讯（共 {len(articles)} 条）：

{articles_text}

请按以下要求输出今日简报：

1. **筛选**：剔除与线香/香道/沉香/檀香/incense/oud 完全无关的内容
2. **分类**：把剩余内容分到这几类：{cats}（没有的类别就写"今日无"）
3. **每条**：一句话摘要（20-40 字）+ 来源 + 链接
4. **开头**：一句话总结今日整体风向
5. **结尾**：如果发现值得关注的新品/价格信号/文化热点，单独列一个"今日重点关注"区块
6. **语言**：中文，简洁直接，不要废话
7. **格式**：纯文本，用 emoji 分区块，不要用 markdown 语法（飞书 text 消息不渲染）

输出："""


def summarize(articles, cfg):
    """调用 LLM 摘要"""
    if not articles:
        return "今日过去 24 小时没有抓到线香相关资讯。"

    client = OpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=cfg["llm"]["base_url"],
    )
    prompt = build_prompt(articles, cfg)
    resp = client.chat.completions.create(
        model=cfg["llm"]["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=cfg["llm"]["temperature"],
    )
    return resp.choices[0].message.content


def get_feishu_token():
    """获取飞书 tenant_access_token"""
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    return resp.json()["tenant_access_token"]


def send_feishu(text, receive_id_type="open_id"):
    """发飞书消息（支持 open_id / phone / email / chat_id）"""
    token = get_feishu_token()
    receive_id = os.environ["FEISHU_RECEIVE_ID"]
    # 自动判断：优先用环境变量；未设置时，收件人含 @ 视为邮箱，否则视为 open_id
    if os.environ.get("FEISHU_RECEIVE_ID_TYPE"):
        receive_id_type = os.environ["FEISHU_RECEIVE_ID_TYPE"]
    elif "@" in receive_id:
        receive_id_type = "email"

    # 飞书 text 消息内容需要 JSON 字符串
    content = '{"text": "' + text.replace('"', '\\"').replace("\n", "\\n") + '"}'

    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        params={"receive_id_type": receive_id_type},
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "receive_id": receive_id,
            "msg_type": "text",
            "content": content,
        },
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书发送失败: {data}")
    print("[OK] 飞书消息已发送", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="线香每日资讯摘要")
    parser.add_argument("--no-send", action="store_true", help="只抓取和摘要，不发送飞书（调试用）")
    args = parser.parse_args()

    cfg = load_config()
    print("开始抓取 RSS...", file=sys.stderr)
    articles = fetch_feeds(cfg)
    print("开始检索公众号（搜狗）...", file=sys.stderr)
    articles += fetch_sogou_wechat(cfg)
    print(f"共抓到 {len(articles)} 条文章", file=sys.stderr)

    print("调用 LLM 摘要...", file=sys.stderr)
    digest = summarize(articles, cfg)

    if args.no_send:
        print("===== 摘要预览（未发送）=====", file=sys.stderr)
        print(digest)
        return

    print("发送飞书...", file=sys.stderr)
    send_feishu(digest)
    print("完成 ✅", file=sys.stderr)


if __name__ == "__main__":
    main()
