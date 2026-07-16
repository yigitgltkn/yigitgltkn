import urllib.request
import json
import re
import os

USERNAME = "yigitgltkn"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

url = f"https://api.github.com/users/{USERNAME}/events/public"
req = urllib.request.Request(url)
req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")

try:
    response = urllib.request.urlopen(req)
    events = json.loads(response.read())
except Exception as e:
    print(f"API Hatası: {e}")
    exit(1)

table = "| 📦 Proje | 🔄 İşlem | 📅 Tarih |\n|---|---|---|\n"

count = 0
for event in events:
    # Hem Push (Commit) hem de PR etkinliklerini yakala
    if event['type'] in ['PushEvent', 'PullRequestEvent'] and count < 5:
        repo_name = event['repo']['name']
        date = event['created_at'][:10]
        
        if event['type'] == 'PushEvent':
            # Atılan commit sayısını al
            commit_count = len(event['payload'].get('commits', []))
            action = f"🚀 {commit_count} Commit"
        else:
            action_type = event['payload']['action']
            action = f"🔄 PR {action_type}"
        
        table += f"| [{repo_name}](https://github.com/{repo_name}) | {action} | {date} |\n"
        count += 1

if count == 0:
    table += "| - | Son 90 günde açık aktivite yok | - |\n"

with open("README.md", "r", encoding="utf-8") as f:
    readme_icerik = f.read()

yeni_readme = re.sub(
    r"(?<=\n).*?(?=\n)",
    table,
    readme_icerik,
    flags=re.DOTALL
)

with open("README.md", "w", encoding="utf-8") as f:
    f.write(yeni_readme)
