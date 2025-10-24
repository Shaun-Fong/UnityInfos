#!/usr/bin/env python3
# coding: utf-8

"""
update_unity_repos_full.py
- 历史 + 增量抓取 Unity 仓库
- 自动去重并生成 README
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
import requests

# ===== 配置 =====
API_TOKEN = os.getenv("API_TOKEN") or os.getenv("PAT_TOKEN") or os.getenv("GITHUB_TOKEN")
if not API_TOKEN:
    print("ERROR: API token not found in env (API_TOKEN / PAT_TOKEN / GITHUB_TOKEN).")
    sys.exit(2)

SEARCH_URL = "https://api.github.com/search/repositories"
QUERY = "unity"       # 关键词，尽量宽松
PER_PAGE = 100        # 每页抓取数量，最大 100
MAX_RESULTS = 100    # Search API 每次最多 1000 条
DATA_FILE = "data/repos.json"
LAST_RUN_FILE = "data/last_run_time.txt"
README_FILE = "README.md"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {API_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "unity-repo-full-script"
}

# ===== 工具函数 =====
def safe_load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_last_run_time():
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, "r") as f:
            return f.read().strip()
    # 默认历史抓取起点：Unity 初始年份
    return "2008-01-01T00:00:00Z"

def set_last_run_time(ts):
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(ts)

def github_search(query, time_field, start_time, end_time=None, per_page=100):
    """
    按时间段抓取仓库，返回列表
    """
    repos = []
    page = 1
    # 构造时间段
    if end_time:
        time_range = f"{start_time}..{end_time}"
        q = f"{query}+{time_field}:{time_range}"
    else:
        q = f"{query}+{time_field}:>{start_time}"

    while True:
        params = {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page
        }
        resp = requests.get(SEARCH_URL, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print(f"ERROR: HTTP {resp.status_code} - {resp.text}")
            break
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        repos.extend(items)
        if len(items) < per_page or len(repos) >= MAX_RESULTS:
            break
        page += 1
        time.sleep(1)  # 避免触发 rate limit
    return repos[:MAX_RESULTS]

def merge_repos(existing, new_repos):
    merged = dict(existing)
    added = 0
    updated = 0
    for r in new_repos:
        key = r.get("full_name")
        if not key:
            continue
        if key not in merged:
            merged[key] = r
            added += 1
        else:
            # 更新逻辑：按 pushed_at 更新
            old_ts = merged[key].get("pushed_at")
            new_ts = r.get("pushed_at")
            if new_ts and old_ts and new_ts > old_ts:
                merged[key] = r
                updated += 1
    return merged, added, updated

def update_readme(repos, filepath=README_FILE):
    """
    生成简单 Markdown README
    """
    lines = [
        "# Unity3D Repositories Collection\n",
        "> 自动生成的 Unity 仓库列表\n",
        f"> Last updated: {datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}\n",
        "---\n",
        "| Name | Stars | Description | Updated |",
        "| ---- | ----- | ----------- | ------- |"
    ]
    # 按 stars 排序
    repo_list = sorted(repos.values(), key=lambda r: r.get("stargazers_count", 0), reverse=True)
    for r in repo_list:
        name = r.get("full_name")
        url = r.get("html_url")
        stars = r.get("stargazers_count", 0)
        desc = r.get("description") or ""
        updated = r.get("pushed_at") or ""
        lines.append(f"| [{name}]({url}) | {stars} | {desc} | {updated} |")

    # 根目录不需要创建目录
    dirpath = os.path.dirname(filepath)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"README.md updated, total repos: {len(repo_list)}")


# ===== 主流程 =====
def main():
    existing = safe_load_json(DATA_FILE)
    last_run_time = get_last_run_time()
    print(f"Last run time: {last_run_time}")

    # 历史抓取模式：按天分段抓取
    start_dt = datetime.strptime(last_run_time, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.utcnow()
    delta = timedelta(days=1)  # 每天一个时间段
    all_new_repos = []

    while start_dt < end_dt:
        next_dt = min(start_dt + delta, end_dt)
        start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"Fetching repos from {start_str} to {end_str} ...")
        created = github_search(QUERY, "created", start_str, end_str, PER_PAGE)
        pushed = github_search(QUERY, "pushed", start_str, end_str, PER_PAGE)
        all_new_repos.extend(created)
        all_new_repos.extend(pushed)
        start_dt = next_dt
        time.sleep(1)  # 防止触发 rate limit

    merged, added, updated = merge_repos(existing, all_new_repos)
    safe_write_json(DATA_FILE, merged)
    print(f"Merged repos -> added: {added}, updated: {updated}, total: {len(merged)}")

    update_readme(merged)
    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    set_last_run_time(now_utc)
    print(f"Updated last_run_time to {now_utc}")

if __name__ == "__main__":
    main()
