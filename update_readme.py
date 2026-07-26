"""GitHub profil README'sindeki dinamik paneli gunceller.

Sadece README.md icindeki PANEL:START / PANEL:END isaretleyicileri
arasindaki blogu degistirir; dosyanin geri kalanina (bio, teknolojiler,
iletisim) asla dokunmaz.

Baglantisiz calisir: harici paket yok, sadece standart kutuphane.
Yerelde token olmadan da calisir (public API, saatlik 60 istek siniri).
"""

import json
import os
import sys
import time
import urllib.request
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
# Actions icinde repo sahibinden gelir, yerelde sabit degere duser
USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER") or "yigitgltkn"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

README_YOLU = "README.md"
BASLANGIC = "<!-- PANEL:START -->"
BITIS = "<!-- PANEL:END -->"

AKTIVITE_LIMIT = 6      # tabloda gosterilecek en fazla aktivite satiri
PROJE_LIMIT = 4         # "Aktif Projeler" tablosundaki repo sayisi
DIL_LIMIT = 5           # dil dagilimi grafigindeki dil sayisi
PENCERE_GUN = 30        # "son X gun" metrikleri
BAR_GENISLIK = 22       # dil grafigi blok genisligi

# Dil dagiliminda sadece son bu kadar aydir dokunulan repolar sayilir.
# Aksi halde 2023'teki Unity projeleri tabloyu %57 C# gosterip guncel
# odagi (Python / TypeScript) gizliyor.
DIL_PENCERE_AY = 24

# Panelin kendisini ureten repo: istatistiklerde ve tabloda gorunmesin
PROFIL_REPOSU = f"{USERNAME}/{USERNAME}"


# --------------------------------------------------------------------------
# GitHub API
# --------------------------------------------------------------------------

def _tek_istek(url):
    istek = urllib.request.Request(url)
    istek.add_header("Accept", "application/vnd.github+json")
    istek.add_header("User-Agent", f"{USERNAME}-profil-paneli")
    if GITHUB_TOKEN:
        istek.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    with urllib.request.urlopen(istek, timeout=30) as yanit:
        return json.loads(yanit.read().decode("utf-8"))


def api(yol, zorunlu=True, deneme=3):
    """API'den JSON getirir. Zorunlu istek basarisiz olursa cikar.

    Kritik nokta: README yazma islemi tum veri toplandiktan SONRA yapilir.
    Boylece API hatasi durumunda dosya oldugu gibi kalir, bozulmaz.
    """
    url = yol if yol.startswith("http") else f"{API}{yol}"
    son_hata = None
    for tur in range(deneme):
        try:
            return _tek_istek(url)
        except Exception as hata:  # urllib.error.*, socket.timeout, JSON hatasi
            son_hata = hata
            if tur < deneme - 1:
                time.sleep(2 * (tur + 1))

    if zorunlu:
        print(f"[HATA] {url} alinamadi: {son_hata}", file=sys.stderr)
        print("README'ye dokunulmadi.", file=sys.stderr)
        sys.exit(1)
    print(f"[UYARI] {url} atlandi: {son_hata}", file=sys.stderr)
    return None


# --------------------------------------------------------------------------
# Yardimcilar
# --------------------------------------------------------------------------

def zaman_coz(damga):
    """'2026-07-25T11:58:07Z' -> timezone bilgili datetime."""
    return datetime.strptime(damga, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def hucre(metin, uzunluk=72):
    """Markdown tablo hucresi icin guvenli metin (bosluk/boru/kisaltma)."""
    if not metin:
        return "—"
    metin = " ".join(metin.split()).replace("|", "\\|")
    if len(metin) > uzunluk:
        metin = metin[: uzunluk - 1].rstrip() + "…"
    return metin


def bar(oran):
    """0.0-1.0 orani blok grafige cevirir."""
    dolu = round(oran * BAR_GENISLIK)
    return "█" * dolu + "░" * (BAR_GENISLIK - dolu)


# --------------------------------------------------------------------------
# Veri toplama
# --------------------------------------------------------------------------

def veri_topla():
    kullanici = api(f"/users/{USERNAME}")
    depolar = api(f"/users/{USERNAME}/repos?per_page=100&sort=pushed") or []
    olaylar = api(f"/users/{USERNAME}/events/public?per_page=100") or []

    # Fork, arsiv ve panelin kendi reposu istatistige girmez:
    # ilk ikisi kendi uretimini yansitmiyor, ucuncusu bu altyapinin kendisi.
    kendi_depolari = [
        d for d in depolar
        if not d.get("fork")
        and not d.get("archived")
        and d["full_name"] != PROFIL_REPOSU
    ]

    return kullanici, kendi_depolari, olaylar


def dil_dagilimi(depolar):
    """Dil dagilimi: her repo esit agirlikta, repo ici oranlarla.

    Sadece DIL_PENCERE_AY icinde push alan repolar sayilir; grafik
    "ne biliyorum" degil "su sira ne yaziyorum" sorusunu cevaplar.

    Ham byte toplami yaniltici oluyor: tek bir statik site reposu tum
    grafigi %50 HTML yapip alti Python projesini gorunmez kiliyor.
    Bu yuzden her repo kendi icinde 1.0'a normalize edilir, yani sonuc
    "repolarimin ortalama dil dagilimi" olur.
    """
    esik = datetime.now(timezone.utc) - timedelta(days=DIL_PENCERE_AY * 30)
    sayac = Counter()

    for depo in depolar:
        itilme = depo.get("pushed_at")  # bos repolarda None olabilir
        if not itilme or zaman_coz(itilme) < esik:
            continue
        diller = api(depo["languages_url"], zorunlu=False)
        if not diller:
            continue
        depo_toplami = sum(diller.values())
        if not depo_toplami:
            continue
        for dil, byte in diller.items():
            sayac[dil] += byte / depo_toplami

    return sayac


def pencere_metrikleri(olaylar):
    """Son PENCERE_GUN gunluk commit sayisi ve dokunulan repo sayisi."""
    esik = datetime.now(timezone.utc) - timedelta(days=PENCERE_GUN)
    commit = 0
    aktif_repolar = set()

    for olay in olaylar:
        if olay["repo"]["name"] == PROFIL_REPOSU:
            continue
        if zaman_coz(olay["created_at"]) < esik:
            continue
        aktif_repolar.add(olay["repo"]["name"])
        if olay["type"] == "PushEvent":
            commit += olay["payload"].get("size") or 1

    return commit, len(aktif_repolar)


def aktivite_satirlari(olaylar):
    """Olaylari (repo + gun + tur) bazinda birlestirir.

    Eski surumdeki hata buydu: ayni gune dusen iki push, tabloda iki ayri
    "1 Commit" satiri uretiyordu. Artik tek satirda toplaniyor.
    """
    gruplar = OrderedDict()  # olaylar yeniden eskiye geldigi icin sira korunur

    for olay in olaylar:
        depo = olay["repo"]["name"]
        if depo == PROFIL_REPOSU:  # botun kendi commit'leri tabloya girmesin
            continue

        tarih = olay["created_at"][:10]
        tur = olay["type"]
        yuk = olay.get("payload") or {}

        if tur == "PushEvent":
            anahtar = (depo, tarih, "push")
            kayit = gruplar.setdefault(anahtar, {"sayi": 0})
            kayit["sayi"] += yuk.get("size") or 1

        elif tur == "PullRequestEvent":
            eylem = yuk.get("action")
            birlesti = (yuk.get("pull_request") or {}).get("merged")
            if eylem == "closed" and birlesti:
                etiket = "Pull request birleştirildi"
            elif eylem == "closed":
                etiket = "Pull request kapatıldı"
            elif eylem == "reopened":
                etiket = "Pull request yeniden açıldı"
            elif eylem == "opened":
                etiket = "Pull request açıldı"
            else:
                continue
            gruplar.setdefault((depo, tarih, etiket), {"sayi": 0})["sayi"] += 1

        elif tur == "CreateEvent" and yuk.get("ref_type") == "repository":
            gruplar.setdefault((depo, tarih, "Yeni repo oluşturuldu"), {"sayi": 1})

        elif tur == "ReleaseEvent" and yuk.get("action") == "published":
            surum = (yuk.get("release") or {}).get("tag_name") or ""
            etiket = f"Sürüm yayınlandı {surum}".strip()
            gruplar.setdefault((depo, tarih, etiket), {"sayi": 1})

        if len(gruplar) >= AKTIVITE_LIMIT * 3:
            break  # limitin cok uzerine cikmaya gerek yok

    satirlar = []
    for (depo, tarih, tur), kayit in list(gruplar.items())[:AKTIVITE_LIMIT]:
        if tur == "push":
            sayi = kayit["sayi"]
            islem = f"`{sayi} commit`"
        else:
            islem = tur if kayit["sayi"] < 2 else f"{tur} ×{kayit['sayi']}"
        satirlar.append((depo, islem, tarih))
    return satirlar


# --------------------------------------------------------------------------
# Panel uretimi
# --------------------------------------------------------------------------

def kart(deger, etiket):
    return f'<td align="center" width="120"><b>{deger}</b><br /><sub>{etiket}</sub></td>'


def panel_olustur(kullanici, depolar, olaylar, diller):
    commit_30, aktif_30 = pencere_metrikleri(olaylar)
    yildiz = sum(d.get("stargazers_count", 0) for d in depolar)
    parcalar = []

    # --- Istatistik kartlari -------------------------------------------
    kartlar = [
        kart(kullanici.get("public_repos", len(depolar)), "Public repo"),
        kart(yildiz, "Yıldız"),
        kart(kullanici.get("followers", 0), "Takipçi"),
        kart(commit_30, f"Commit / {PENCERE_GUN} gün"),
        kart(aktif_30, f"Aktif proje / {PENCERE_GUN} gün"),
    ]
    parcalar.append("#### Profil Özeti\n")
    parcalar.append(
        '<table>\n  <tr>\n    ' + "\n    ".join(kartlar) + "\n  </tr>\n</table>\n"
    )

    # --- Dil dagilimi --------------------------------------------------
    if diller:
        toplam = sum(diller.values())
        en_iyi = diller.most_common(DIL_LIMIT)
        genislik = max(len(ad) for ad, _ in en_iyi)
        satirlar = [
            f"{ad.ljust(genislik)}  {bar(byte / toplam)}  {byte / toplam * 100:5.1f}%"
            for ad, byte in en_iyi
        ]
        parcalar.append("#### Teknoloji Dağılımı\n")
        parcalar.append(
            f"<sub>son {DIL_PENCERE_AY} ayda güncellenen depolar · "
            f"repo başına normalize edilmiş</sub>\n"
        )
        parcalar.append("```text\n" + "\n".join(satirlar) + "\n```\n")

    # --- Son aktiviteler -----------------------------------------------
    parcalar.append("#### Son Aktiviteler\n")
    tablo = ["| Proje | İşlem | Tarih |", "|:--|:--|--:|"]
    satirlar = aktivite_satirlari(olaylar)
    if satirlar:
        for depo, islem, tarih in satirlar:
            ad = depo.split("/", 1)[-1]
            tablo.append(f"| [{ad}](https://github.com/{depo}) | {islem} | {tarih} |")
    else:
        tablo.append("| — | Son 90 günde public aktivite yok | — |")
    parcalar.append("\n".join(tablo) + "\n")

    # --- Aktif projeler ------------------------------------------------
    projeler = depolar[:PROJE_LIMIT]  # API sort=pushed ile geldi: en yeni ustte
    if projeler:
        parcalar.append("#### Aktif Projeler\n")
        tablo = ["| Proje | Açıklama | Dil | ★ |", "|:--|:--|:--|--:|"]
        for depo in projeler:
            tablo.append(
                f"| [{hucre(depo['name'], 28)}]({depo['html_url']}) "
                f"| {hucre(depo.get('description'), 70)} "
                f"| {depo.get('language') or '—'} "
                f"| {depo.get('stargazers_count', 0)} |"
            )
        parcalar.append("\n".join(tablo) + "\n")

    # --- Altbilgi ------------------------------------------------------
    simdi = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    parcalar.append(
        f'<sub>Bu panel GitHub Actions tarafından otomatik üretilir · '
        f"son güncelleme {simdi} UTC</sub>"
    )

    return "\n".join(parcalar)


# --------------------------------------------------------------------------
# README yazma
# --------------------------------------------------------------------------

def readme_guncelle(panel):
    with open(README_YOLU, "r", encoding="utf-8") as dosya:
        icerik = dosya.read()

    blok = f"{BASLANGIC}\n\n{panel}\n\n{BITIS}"

    bas = icerik.find(BASLANGIC)
    son = icerik.find(BITIS)
    if bas != -1 and son > bas:
        # Sadece iki isaretleyici arasi degisir. Duz dilim kullaniyoruz;
        # re.sub olsa panel icindeki \g gibi diziler kacis karakteri sanilirdi.
        yeni = icerik[:bas] + blok + icerik[son + len(BITIS):]
    else:
        print("[UYARI] Isaretleyici bulunamadi, panel dosya sonuna eklendi.",
              file=sys.stderr)
        yeni = icerik.rstrip() + "\n\n" + blok + "\n"

    if yeni == icerik:
        print("Degisiklik yok.")
        return

    with open(README_YOLU, "w", encoding="utf-8", newline="\n") as dosya:
        dosya.write(yeni)
    print(f"README guncellendi ({len(yeni)} karakter).")


def main():
    kullanici, depolar, olaylar = veri_topla()
    diller = dil_dagilimi(depolar)
    readme_guncelle(panel_olustur(kullanici, depolar, olaylar, diller))


if __name__ == "__main__":
    main()
