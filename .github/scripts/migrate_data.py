import json
import os

DATA_FILE = ".github/data/repos.json"
ARCHIVE_DIR = ".github/data/archive"

os.makedirs(ARCHIVE_DIR, exist_ok=True)

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

archives = {}

for repo in data.values():
    year = repo["created_at"][:4]
    archives.setdefault(year, []).append(repo)

for year, repos in archives.items():
    path = f"{ARCHIVE_DIR}/{year}.json"

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    existing_map = {r["full_name"]: r for r in existing}

    for r in repos:
        existing_map[r["full_name"]] = r

    with open(path, "w", encoding="utf-8") as f:
        json.dump(list(existing_map.values()), f, ensure_ascii=False)

print("Migration completed.")
