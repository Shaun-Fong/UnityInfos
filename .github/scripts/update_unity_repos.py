#!/usr/bin/env python3
# coding: utf-8

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
QUERY = "unity"
PER_PAGE = 100
MAX_RESULTS = 100
DATA_FILE = "data/repos.json"
LAST_RUN_FILE = "data/last_run_time.txt"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {API_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "unity-repo-test-script"
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
    # 测试时可手动设置
    return (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

def set_last_run_time(ts):
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(ts)

# ===== 抓取函数 =====
def fetch_repos(query, time_field, since, per_page=5, max_results=100):
    repos = []
    page = 1
    while len(repos) < max_results:
        q = f"{query}+{time_field}:>{since}"
        params = {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page
        }
        resp = requests.get(SEARCH_URL, headers=HEADERS, params=params)
        print(f"API request page {page} status: {resp.status_code}")
        print(json.dumps(resp.json(), indent=2))  # 打印返回 JSON
        if resp.status_code != 200:
            print(f"ERROR: HTTP {resp.status_code}")
            break
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        repos.extend(items)
        if len(items) < per_page:
            break
        page += 1
        time.sleep(1)
    return repos[:max_results]

# ===== 主流程 =====
def main():
    existing = safe_load_json(DATA_FILE)
    last_run_time = get_last_run_time()
    print(f"Last run time: {last_run_time}")

    print("Fetching newly created repos...")
    created_repos = fetch_repos(QUERY, "created", last_run_time, PER_PAGE, MAX_RESULTS)
    print(f"Fetched {len(created_repos)} created repos.\n")

    print("Fetching recently pushed repos...")
    pushed_repos = fetch_repos(QUERY, "pushed", last_run_time, PER_PAGE, MAX_RESULTS)
    print(f"Fetched {len(pushed_repos)} pushed repos.\n")

    # 合并逻辑（简单去重）
    merged = dict(existing)
    for r in created_repos + pushed_repos:
        key = r.get("full_name")
        if key and key not in merged:
            merged[key] = r
    safe_write_json(DATA_FILE, merged)
    print(f"Data saved, total repos: {len(merged)}")

    # 更新 last_run_time
    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    set_last_run_time(now_utc)
    print(f"Updated last_run_time to {now_utc}")

if __name__ == "__main__":
    main()
