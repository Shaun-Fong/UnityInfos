import requests
import json
import os
from datetime import datetime, timedelta
import time
from collections import defaultdict

# ================= 配置 =================
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")  # GitHub Actions secret
DATA_FILE = ".github/data/repos.json"
LAST_RUN_FILE = ".github/data/last_run_time.txt"
README_FILE = "README.md"

QUERY = "unity OR unity3d"
BATCH_DAYS = 1
PER_PAGE = 100
MAX_RESULTS = 1000
TOTAL_FETCH_LIMIT = 3000
REQUEST_DELAY = 2
MAX_DESC_LENGTH = 100

# ================= 辅助函数 =================
def load_last_run():
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, "r") as f:
            return f.read().strip()
    else:
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

        for repo in items:
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
            if existing[key]["updated_at"] != updated_at:
                existing[key]["updated_at"] = updated_at
                existing[key]["stargazers_count"] = repo.get("stargazers_count", 0)
                updated += 1
    print(f"Merged repos -> added: {added}, updated: {updated}, total: {len(existing)}")
    return existing


# ================= 输出部分 =================
def truncate(s, max_len):
    if not s: return ""
    return s if len(s) <= max_len else s[:max_len - 3] + "..."

def write_repo_table(filepath, repo_list, title):
    """输出单个 markdown 表格文件"""
    NAME_DISPLAY_MAX = 20
    DESC_DISPLAY_MAX = 120

    lines = [f"# {title}", "", "| Name | Stars | Description | Updated |", "| ---- | -----:| ----------- | ------- |"]

    for repo in sorted(repo_list, key=lambda x: x.get("stargazers_count", 0), reverse=True):
        full_name = repo["full_name"]
        name = full_name.split("/", 1)[-1]
        url = repo["html_url"]
        desc = truncate(repo.get("description", "").replace("\n", " "), DESC_DISPLAY_MAX)
        updated = repo.get("updated_at", "").split("T")[0]
        stars = repo.get("stargazers_count", 0)
        lines.append(f"| [{name}]({url}) | {stars} | {desc} | {updated} |")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {len(repo_list)} repos to {filepath}")

def generate_daily_files(repos):
    """按创建日期生成 YYYY/MM_DD.md 文件"""
    grouped = defaultdict(list)
    for repo in repos.values():
        if not repo.get("description") or repo.get("stargazers_count", 0) <= 1:
            continue
        created = repo["created_at"][:10]  # YYYY-MM-DD
        year, month, day = created.split("-")
        grouped[(year, month, day)].append(repo)

    for (year, month, day), repo_list in sorted(grouped.items()):
        os.makedirs(year, exist_ok=True)
        filename = f"{year}/{month}_{day}.md"
        title = f"Unity Repositories created on {year}-{month}-{day}"
        write_repo_table(filename, repo_list, title)

def update_readme(repos):
    """生成按年份折叠的 README.md"""
    # 先筛选有效仓库（有描述且 Star > 2）
    valid_repos = [r for r in repos.values() if r.get("description") and r.get("stargazers_count", 0) > 2]

    # 按年份分组
    years = defaultdict(list)
    for repo in valid_repos:
        created = repo["created_at"][:10]  # YYYY-MM-DD
        year = created.split("-")[0]
        years[year].append(repo)

    # 按年份排序
    sorted_years = sorted(years.keys(), reverse=True)

    lines = []
    lines.append("# Unity3D Repositories Collection")
    lines.append(f"> Last updated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("")
    lines.append(f"仓库总数：{len(valid_repos)}")
    lines.append("")

    for year in sorted_years:
        repo_list = sorted(years[year], key=lambda x: x.get("stargazers_count", 0), reverse=True)
        lines.append(f"<details>")
        lines.append(f"<summary>{year} - {len(repo_list)} repositories</summary>")
        lines.append("")  # 空行
        # 列出仓库信息
        for repo in repo_list:
            full_name = repo["full_name"]
            stars = repo.get("stargazers_count", 0)
            desc = repo.get("description", "").replace("\n", " ").strip()
            lines.append(f"- [{full_name}]({repo['html_url']}) - ⭐ {stars} - {desc}")
        lines.append("")  # 空行
        lines.append("</details>")
        lines.append("")  # 每个年份之间留空行

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"README.md updated with yearly foldable sections (total repos: {len(valid_repos)})")


def generate_top1000(repos, filename="top1000.md"):
    """生成 star 数量前 1000 的仓库列表"""
    sorted_repos = sorted(
        [r for r in repos.values() if r.get("stargazers_count", 0) > 1],
        key=lambda x: x["stargazers_count"],
        reverse=True
    )[:1000]

    lines = [
        "# Top 1000 Unity3D Repositories (by Stars)",
        f"> Last updated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}",
        ""
    ]

    for repo in sorted_repos:
        full_name = repo["full_name"]
        stars = repo["stargazers_count"]
        url = repo["html_url"]
        lines.append(f"[{full_name}]({url}) - ⭐ {stars}\n")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Top 1000 list generated, total: {len(sorted_repos)}")


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

    while last_run_date < now and total_fetched < TOTAL_FETCH_LIMIT:
        batch_end = min(last_run_date + timedelta(days=BATCH_DAYS), now)
        fetched = fetch_repos(last_run_date, batch_end)

        if total_fetched + len(fetched) > TOTAL_FETCH_LIMIT:
            fetched = fetched[:TOTAL_FETCH_LIMIT - total_fetched]

        existing = merge_repos(existing, fetched)
        save_repos(existing)

        total_fetched += len(fetched)
        print(f"Total fetched in this run: {total_fetched} / {TOTAL_FETCH_LIMIT}")

        if total_fetched >= TOTAL_FETCH_LIMIT:
            print("Reached total fetch limit for this run. Stopping batch fetch.")
            save_last_run(last_run_date.strftime("%Y-%m-%dT%H:%M:%SZ"))
            break
        else:
            last_run_date = batch_end
            save_last_run(last_run_date.strftime("%Y-%m-%dT%H:%M:%SZ"))

        time.sleep(REQUEST_DELAY)

    # 输出所有结果
    generate_daily_files(existing)
    update_readme(existing)
    generate_top1000(existing)

if __name__ == "__main__":
    main()
