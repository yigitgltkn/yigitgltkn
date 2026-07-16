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

# Başlığı artık Python scriptimizin içine aldık
table = "### 🚀 Son Aktiviteler\n\n| 📦 Proje | 🔄 İşlem | 📅 Tarih |\n|---|---|---|\n"

count = 0
for event in events:
    repo_name = event['repo']['name']
    
    # Botun profili güncellediği kendi işlemlerini tablodan gizle
    if repo_name == f"{USERNAME}/{USERNAME}":
        continue
        
    if event['type'] in ['PushEvent', 'PullRequestEvent'] and count < 5:
        date = event['created_at'][:10]
        
        if event['type'] == 'PushEvent':
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

# KESİN ÇÖZÜM: Dosyadaki tüm kopyalanmış tabloları ve başlıkları bulup yokediyoruz
temiz_readme = re.sub(r".*?", "", readme_icerik, flags=re.DOTALL)
temiz_readme = re.sub(r"### 🚀 Son Aktiviteler", "", temiz_readme).strip()

# Temizlenmiş dosyanın en sonuna sadece 1 tane yeni tablo ekliyoruz
yeni_readme = f"{temiz_readme}\n\n\n{table}\n\n"

with open("README.md", "w", encoding="utf-8") as f:
    f.write(yeni_readme)
