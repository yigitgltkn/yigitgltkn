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
    repo_name = event['repo']['name']
    
    # 1. ÇÖZÜM: Botun profili güncellediği kendi işlemlerini tablodan gizle
    if repo_name == f"{USERNAME}/{USERNAME}":
        continue
        
    if event['type'] in ['PushEvent', 'PullRequestEvent'] and count < 5:
        date = event['created_at'][:10]
        
        if event['type'] == 'PushEvent':
            # 2. ÇÖZÜM: 'size' ile gerçek commit sayısını al, bulamazsa en az 1 yaz.
            commit_count = event['payload'].get('size', 1)
            action = f"🚀 {commit_count} Commit"
        else:
            action_type = event['payload']['action']
            action = f"🔄 PR {action_type}"
        
        table += f"| [{repo_name}](https://github.com/{repo_name}) | {action} | {date} |\n"
        count += 1

if count == 0:
    table += "| - | Yakın zamanda açık kaynak aktivitesi yok | - |\n"

with open("README.md", "r", encoding="utf-8") as f:
    readme_icerik = f.read()

# 3. ÇÖZÜM: Etiketlerin (tags) içini silmek yerine etiketlerle birlikte temiz bir şekilde baştan yaz (Sonsuz tablo sorununu çözer)
pattern = r".*?"
replacement = f"\n{table}\n"

yeni_readme = re.sub(pattern, replacement, readme_icerik, flags=re.DOTALL)

with open("README.md", "w", encoding="utf-8") as f:
    f.write(yeni_readme)
