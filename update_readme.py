import urllib.request
import json
import re
import os

# GitHub kullanıcı adını buraya yaz
USERNAME = "yigitgltkn"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# GitHub API'den son etkinlikleri çek
url = f"https://api.github.com/users/{USERNAME}/events/public"
req = urllib.request.Request(url)
req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")

try:
    response = urllib.request.urlopen(req)
    events = json.loads(response.read())
except Exception as e:
    print(f"API Hatası: {e}")
    exit(1)

# Tablo başlıklarını oluştur
table = "| 📦 Proje | 🔄 İşlem | 📅 Tarih |\n|---|---|---|\n"

# Sadece Pull Request (PR) etkinliklerini filtrele ve ilk 5 tanesini al
count = 0
for event in events:
    if event['type'] == 'PullRequestEvent' and count < 5:
        repo_name = event['repo']['name']
        action = event['payload']['action'] # opened, closed vb.
        date = event['created_at'][:10]
        
        # Tabloya satır olarak ekle
        table += f"| [{repo_name}](https://github.com/{repo_name}) | PR {action} | {date} |\n"
        count += 1

# Eğer hiç PR yoksa boş kalmasın diye bir mesaj ekle
if count == 0:
    table += "| - | Şu an yakın zamanda PR bulunmuyor | - |\n"

# README dosyasını oku
with open("README.md", "r", encoding="utf-8") as f:
    readme_icerik = f.read()

# Yer tutucuların (placeholder) arasını bul ve yeni tabloyla değiştir
yeni_readme = re.sub(
    r"(?<=<!-- START_SECTION:activity -->\n).*?(?=\n<!-- END_SECTION:activity -->)",
    table,
    readme_icerik,
    flags=re.DOTALL
)

# Güncellenmiş metni README'ye yaz
with open("README.md", "w", encoding="utf-8") as f:
    f.write(yeni_readme)
