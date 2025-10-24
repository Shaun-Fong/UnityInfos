#!/usr/bin/env python3
# coding: utf-8
"""
update_unity_repos_incremental.py
- 基于时间段增量抓取 GitHub 仓库（创建时间或最近 push）
- 每次只抓取 last_run_time 之后新增/更新的仓库
- 以 full_name 去重合并到 data/repos.json
- 生成 README.md
- 更新 last_run_time
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List

# ===== 配置 =====
API_TOKEN = os.getenv("API_TOKEN") or os.getenv("PAT_TOKEN") or os.getenv("GITHUB_TOKEN")
if not API_TOKEN:
    print("ERROR: API token not found in env (API_TOKEN / PAT_TOKEN / GITHUB_TOKEN).")
    sys.exit(2)

SEARCH_URL = "https://api.github.com/search/repositories"
QUERY = "unity"
PER_PAGE = 5
MAX_RESULTS = 100
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "repos.json")
README_FILE = "README.md"
LAST_RUN_FILE = os.path.join(DATA_DIR, "last_run_time.txt")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {API_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "unity-repo-updater-script"
}

# ===== 工具函数 =====
def safe_load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_write_json(path: str, data: Dict[str, Any]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def iso_to_datetime(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")

def get_last_run_time() -> str:
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, "r") as f:
            return f.read().strip()
    # 如果没有记录，默认抓取最近 24 小时
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

def set_last_run_time(ts: str):
    os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(ts)

# ===== 抓取函数 =====
def fetch_repos(query: str, time_field: str, since: str, per_page: int = 100, max_results: int = 1000) -> List[Dict[str, Any]]:
    """
    time_field: 'created' 或 'pushed'
    since: ISO 格式 UTC 时间字符串
    """
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
        if resp.status_code == 422:
            print("Search API 422：超过 GitHub 搜索上限（最多 1000 条）")
            break
        if resp.status_code != 200:
            print(f"ERROR: HTTP {resp.status_code} - {resp.text}")
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

# ===== 合并逻辑 =====
def merge_repos(existing: Dict[str, Any], fetched_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    added = 0
    updated = 0
    skipped = 0
    merged = dict(existing)
    for r in fetched_list:
        key = r.get("full_name")
        if not key:
            continue
        minimal = {
            "full_name": r.get("full_name"),
            "html_url": r.get("html_url"),
            "description": r.get("description"),
            "stargazers_count": r.get("stargazers_count"),
            "language": r.get("language"),
            "topics": r.get("topics") or [],
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at")
        }
        if key not in merged:
            minimal["_imported_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            merged[key] = minimal
            added += 1
        else:
            existing_updated = merged[key].get("updated_at")
            try:
                if r.get("updated_at") and existing_updated and iso_to_datetime(r["updated_at"]) > iso_to_datetime(existing_updated):
                    merged[key].update(minimal)
                    merged[key]["_imported_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                    updated += 1
                else:
                    skipped += 1
            except Exception:
                merged[key].update(minimal)
                merged[key]["_imported_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                updated += 1
    print(f"Merging result -> added: {added}, updated: {updated}, skipped: {skipped}")
    return merged

# ===== README 渲染 =====
def render_readme(merged_repos: Dict[str, Any], top_per_category: int = 30) -> str:
    repo_list = list(merged_repos.values())
    repo_list.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    categories = {}
    for r in repo_list:
        desc = (r.get("description") or "").lower()
        if any(k in desc for k in ["shader", "render", "graphics", "lighting"]):
            cat = "Graphics / Shader"
        elif any(k in desc for k in ["editor", "tool", "plugin", "extension"]):
            cat = "Editor Tools"
        elif any(k in desc for k in ["ai", "navmesh", "pathfinding", "behavior"]):
            cat = "AI / Navigation"
        elif any(k in desc for k in ["network", "multiplayer", "p2p", "server"]):
            cat = "Networking"
        elif any(k in desc for k in ["game", "sample", "demo", "project"]):
            cat = "Complete Projects"
        else:
            cat = "Other"
        categories.setdefault(cat, []).append(r)
    md = []
    md.append("# Unity3D Projects Collection\n")
    md.append(f"_Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%SZ')}_\n")
    md.append("\n---\n")
    for cat, items in categories.items():
        md.append(f"## {cat}\n")
        md.append("| Project | Stars | Description | Updated |")
        md.append("|---|---:|---|---|")
        for r in items[:top_per_category]:
            name = r.get("full_name")
            url = r.get("html_url")
            stars = r.get("stargazers_count", 0)
            desc = (r.get("description") or "").replace("\n", " ").replace("|", "｜")
            updated = r.get("updated_at", "")[:10]
            md.append(f"| [{name}]({url}) | {stars} | {desc} | {updated} |")
        md.append("\n")
    md.append("\n---\n")
    #md.append("> 数据来自 GitHub Search API（增量更新，每小时自动合并历史数据）。\n")
    return "\n".join(md)

# ===== 主流程 =====
def main():
    # 1) 读取历史数据
    existing = {}
    if os.path.exists(DATA_FILE):
        try:
            existing = safe_load_json(DATA_FILE)
            if isinstance(existing, list):
                existing = {r["full_name"]: r for r in existing if "full_name" in r}
        except Exception as e:
            print("WARN: 读取 data/repos.json 失败，使用空数据。", e)
            existing = {}
    else:
        existing = {}

    # 2) 获取 last_run_time
    last_run_time = get_last_run_time()
    print(f"Last run time: {last_run_time}")

    # 3) 抓取新增创建和更新的仓库
    print("Fetching newly created repos...")
    created_repos = fetch_repos(QUERY, "created", last_run_time, PER_PAGE, MAX_RESULTS)
    print(f"Fetched {len(created_repos)} created repos.")

    print("Fetching recently pushed repos...")
    pushed_repos = fetch_repos(QUERY, "pushed", last_run_time, PER_PAGE, MAX_RESULTS)
    print(f"Fetched {len(pushed_repos)} pushed repos.")

    all_fetched = created_repos + pushed_repos

    # 4) 合并
    merged = merge_repos(existing, all_fetched)

    # 5) 写回 data/repos.json
    safe_write_json(DATA_FILE, merged)
    print("Wrote updated data/repos.json")

    # 6) 生成 README
    new_readme = render_readme(merged)
    old_readme = ""
    if os.path.exists(README_FILE):
        with open(README_FILE, "r", encoding="utf-8") as f:
            old_readme = f.read()
    if new_readme != old_readme:
        with open(README_FILE, "w", encoding="utf-8") as f:
            f.write(new_readme)
        print("README.md updated")
    else:
        print("No changes in README.md")

    # 7) 更新 last_run_time
    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    set_last_run_time(now_utc)
    print(f"Updated last_run_time to {now_utc}")

    print("=== SUMMARY ===")
    print(f"Total fetched: {len(all_fetched)}, Repos in data: {len(merged)}")

if __name__ == "__main__":
    main()
