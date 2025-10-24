import os
import requests
import datetime

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"}

QUERY = "unity3d"
PER_PAGE = 100
MAX_RESULTS = 1000  # 每小时最多获取1000条

def fetch_repos(query):
    repos = []
    page = 1
    while len(repos) < MAX_RESULTS:
        url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={PER_PAGE}&page={page}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            print(f"请求失败：{r.status_code} {r.text}")
            break
        data = r.json()
        items = data.get("items", [])
        if not items:
            break
        repos.extend(items)
        if len(items) < PER_PAGE:
            break
        page += 1
    return repos[:MAX_RESULTS]


def classify_repo(repo):
    """根据仓库描述进行简单分类"""
    desc = (repo.get("description") or "").lower()
    topics = repo.get("topics", [])

    if any(k in desc for k in ["shader", "render", "graphics"]):
        category = "Graphics/Shader"
    elif any(k in desc for k in ["editor", "tool", "plugin"]):
        category = "Editor Tools"
    elif any(k in desc for k in ["ai", "navmesh", "pathfind"]):
        category = "AI / Navigation"
    elif any(k in desc for k in ["network", "multiplayer"]):
        category = "Networking"
    elif any(k in desc for k in ["animation", "animator"]):
        category = "Animation"
    else:
        category = "Other"

    return category


def update_readme(repos):
    readme_path = "README.md"
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            original_content = f.read()
    else:
        original_content = "# Unity3D Projects Collection\n\n"

    sections = {}
    for repo in repos:
        category = classify_repo(repo)
        repo_line = f"- [{repo['full_name']}]({repo['html_url']}) ⭐ {repo['stargazers_count']} — {repo.get('description', '')}"
        sections.setdefault(category, []).append(repo_line)

    new_content = "# 🧩 Unity3D Projects Collection\n\n"
    new_content += f"_Last updated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}_\n\n"
    for cat, items in sections.items():
        new_content += f"## {cat}\n" + "\n".join(items) + "\n\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("README updated successfully.")


if __name__ == "__main__":
    print("Fetching Unity3D repos...")
    repos = fetch_repos(QUERY)
    print(f"Total fetched: {len(repos)} repos")
    update_readme(repos)
