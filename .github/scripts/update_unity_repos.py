# Chatgpt还是太好用了 XD

import requests
import json
import os
from datetime import datetime, timedelta
import time

# ================= 配置 =================
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # GitHub Actions secret
DATA_FILE = ".github/data/repos.json"
LAST_RUN_FILE = ".github/data/last_run_time.txt"
README_FILE = "README.md"

QUERY = "unity OR unity3d"
BATCH_DAYS = 1           # 每批抓取的天数
PER_PAGE = 100           # 每页抓取数量
MAX_RESULTS = 1000       # 每次搜索最大结果数（GitHub API 限制）
TOTAL_FETCH_LIMIT = 1000 # 每次脚本执行抓取总数限制
REQUEST_DELAY = 2        # 秒，避免触发 API rate limit
MAX_DESC_LENGTH = 100    # description 最大长度

# ================= 辅助函数 =================
def load_last_run():
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, "r") as f:
            return f.read().strip()
    else:
        # 初始抓取时间
        return "2020-01-01T00:00:00Z"

def save_last_run(ts):
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(ts)

def load_existing_repos():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_repos(data):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ================= API 请求 =================
def fetch_repos(start_date, end_date):
    all_items = []
    page = 1
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    while True:
        q = f"{QUERY}+created:{start_str}..{end_str}"
        url = f"https://api.github.com/search/repositories?q={q}&per_page={PER_PAGE}&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            print("ERROR:", resp.status_code, resp.text)
            break
        data = resp.json()
        items = data.get("items", [])

        for i, repo in enumerate(items, start=1 + len(all_items)):
            # 跳过没有 description 的仓库
            if not repo.get("description"):
                continue

            all_items.append(repo)
            print(f"Fetched {len(all_items)} / (max {MAX_RESULTS}) from {start_str} to {end_str}: {repo['full_name']}")

            if len(all_items) >= MAX_RESULTS:
                break

        if len(items) < PER_PAGE or len(all_items) >= MAX_RESULTS:
            break
        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"Fetched {len(all_items)} repos from {start_str} to {end_str} (with description)")
    return all_items

# ================= 合并增量 =================
def merge_repos(existing, fetched):
    added = 0
    updated = 0
    for repo in fetched:
        key = repo["full_name"]
        created_at = repo["created_at"]
        updated_at = repo["updated_at"]

        if key not in existing:
            existing[key] = {
                "name": repo["name"],
                "full_name": key,
                "html_url": repo["html_url"],
                "description": repo.get("description") or "",
                "stargazers_count": repo.get("stargazers_count", 0),
                "created_at": created_at,
                "updated_at": updated_at
            }
            added += 1
        else:
            # 更新最后更新时间
            if existing[key]["updated_at"] != updated_at:
                existing[key]["updated_at"] = updated_at
                updated += 1
    print(f"Merged repos -> added: {added}, updated: {updated}, total: {len(existing)}")
    return existing

def update_readme(repos):
    """
    生成 Markdown 表格版 README（服务器端截断，避免水平滚动）
    - 只展示有 description 的仓库
    - 只展示 star > 1 的仓库
    - 截断 repo 名称和 description，超出部分以 "..." 表示
    - 在链接中使用 title 属性保存完整信息，鼠标悬停可查看（tooltip）
    """
    NAME_DISPLAY_MAX = 36   # 仓库名称显示最大长度
    DESC_DISPLAY_MAX = 120  # 描述显示最大长度

    def clean_text(s: str) -> str:
        """清理文本，去掉换行和表格冲突字符"""
        if not s:
            return ""
        return s.replace("\n", " ").replace("|", "｜").strip()

    def truncate(s: str, max_len: int) -> str:
        """按字符截断，超出加省略号"""
        if not s:
            return ""
        if len(s) <= max_len:
            return s
        return s[:max_len - 3].rstrip() + "..."

    lines = []
    lines.append("# Unity3D Repositories Collection")
    lines.append(f"> Last updated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("| Name | Stars | Description | Updated |")
    lines.append("| ---- | -----:| ----------- | ------- |")

    # 仅保留：有 description 且 star > 1
    repos_filtered = [
        r for r in repos.values()
        if r.get("description") and r.get("stargazers_count", 0) > 1
    ]

    # 按 star 数量排序（降序）
    sorted_repos = sorted(repos_filtered, key=lambda x: x.get("stargazers_count", 0), reverse=True)

    for repo in sorted_repos:
        full_name = repo.get("full_name", "")
        url = repo.get("html_url", "")
        stars = repo.get("stargazers_count", 0)
        display_name = full_name.split("/", 1)[-1] if "/" in full_name else full_name

        desc_raw = clean_text(repo.get("description", "") or "")
        desc_display = truncate(desc_raw, DESC_DISPLAY_MAX)
        name_display = truncate(display_name, NAME_DISPLAY_MAX)

        # 链接 + tooltip
        link_html = f'<a href="{url}" title="{full_name}">{name_display}</a>'
        desc_html = f'<span title="{desc_raw}">{desc_display}</span>'
        updated = repo.get("updated_at", "").split("T")[0] if repo.get("updated_at") else ""

        lines.append(f"| {link_html} | {stars} | {desc_html} | {updated} |")

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"README.md updated, total repos shown: {len(sorted_repos)} (stars > 1, with description)")


# ================= 主逻辑 =================
def main():
    last_run_str = load_last_run()
    try:
        last_run_date = datetime.strptime(last_run_str, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        last_run_date = datetime.strptime(last_run_str, "%Y-%m-%d")
        last_run_str = last_run_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    now = datetime.utcnow()
    existing = load_existing_repos()
    total_fetched = 0

    # 分 batch 抓取历史数据
    while last_run_date < now and total_fetched < TOTAL_FETCH_LIMIT:
        batch_end = min(last_run_date + timedelta(days=BATCH_DAYS), now)
        fetched = fetch_repos(last_run_date, batch_end)

        # 超过总抓取限制则截断
        if total_fetched + len(fetched) > TOTAL_FETCH_LIMIT:
            fetched = fetched[:TOTAL_FETCH_LIMIT - total_fetched]

        existing = merge_repos(existing, fetched)
        save_repos(existing)
        update_readme(existing)

        total_fetched += len(fetched)
        print(f"Total fetched in this run: {total_fetched} / {TOTAL_FETCH_LIMIT}")

        # 如果超过总抓取限制，在中途停止，不推进 last_run_date
        if total_fetched >= TOTAL_FETCH_LIMIT:
            print("Reached total fetch limit for this run. Stopping batch fetch.")
            # 因为当前 batch 没抓完，所以不要推进日期
            save_last_run(last_run_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
            break
        else:
            # 当前 batch 抓取完成，推进日期
            last_run_date = batch_end
            save_last_run(last_run_date.strftime("%Y-%m-%dT%H:%M:%SZ"))

        time.sleep(REQUEST_DELAY)

if __name__ == "__main__":
    main()
