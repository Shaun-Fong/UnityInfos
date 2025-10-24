#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_unity_repos.py
每小时执行一次，使用 GitHub API 获取 Unity3D 相关仓库，并分类追加到 README.md。
"""

import requests
import os
import time
from datetime import datetime

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # 从GitHub Actions环境变量读取
SEARCH_URL = "https://api.github.com/search/repositories"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

def fetch_repositories():
    """调用GitHub API获取Unity3D相关仓库"""
    repos = []
    params = {
        "q": "unity3d language:C#",
        "sort": "stars",
        "order": "desc",
        "per_page": 100,
        "page": 1,
    }

    # 目标：获取约3000条数据（每次100条，共30页）
    for i in range(1, 31):
        params["page"] = i
        resp = requests.get(SEARCH_URL, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print("请求失败：", resp.status_code, resp.text)
            break
        data = resp.json()
        if "items" not in data:
            break
        repos.extend(data["items"])
        time.sleep(2)
    return repos


def classify_repo(repo):
    """根据描述或名称进行简单分类"""
    text = (repo.get("description") or "").lower()
    name = repo["name"].lower()
    if any(k in text for k in ["shader", "render", "lighting", "graphics"]):
        return "Rendering / Shader"
    elif any(k in text for k in ["editor", "tool", "extension", "inspector"]):
        return "Editor Tools"
    elif any(k in text for k in ["ai", "navmesh", "behavior", "pathfinding"]):
        return "AI / Navigation"
    elif any(k in text for k in ["network", "multiplayer", "server"]):
        return "Networking"
    elif any(k in text for k in ["game", "project", "sample"]):
        return "Complete Projects"
    else:
        return "Miscellaneous"


def generate_markdown(repos):
    """生成新的Markdown表格"""
    categorized = {}
    for repo in repos:
        category = classify_repo(repo)
        categorized.setdefault(category, []).append(repo)

    md = []
    md.append(f"## Unity3D Projects (updated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')})\n")
    for cat, items in categorized.items():
        md.append(f"### {cat}\n")
        md.append("| Project | Stars | Description | Updated |")
        md.append("|----------|--------|-------------|----------|")
        for r in items[:30]:  # 每类最多显示30条
            md.append(f"| [{r['full_name']}]({r['html_url']}) | ⭐ {r['stargazers_count']} | "
                      f"{(r['description'] or '').replace('|', ',')} | {r['updated_at'][:10]} |")
        md.append("")
    return "\n".join(md)


def update_readme(new_section):
    """读取现有README并插入新内容"""
    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    start_marker = "<!--UNITY_START-->"
    end_marker = "<!--UNITY_END-->"

    if start_marker in content and end_marker in content:
        before = content.split(start_marker)[0]
        after = content.split(end_marker)[1]
        updated = f"{before}{start_marker}\n{new_section}\n{end_marker}{after}"
    else:
        # 若README中无标记，则直接追加
        updated = f"{content}\n\n{start_marker}\n{new_section}\n{end_marker}\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(updated)


if __name__ == "__main__":
    print("Fetching Unity3D repos...")
    repos = fetch_repositories()
    print(f"Total fetched: {len(repos)} repos")

    md_content = generate_markdown(repos)
    update_readme(md_content)
    print("README updated successfully.")
