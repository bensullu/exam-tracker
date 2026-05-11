# 📊 Dershane Sinav Sonuc Takip Sistemi

Sinav sonuc PDF'lerini otomatik parse eden, veritabaninda saklayan ve grafik raporlar olusturan bir uygulama.

## Ozellikler

- **Otomatik PDF Parsing** — MOBESE ve SORUNET/LGS formatlarini otomatik algilar
- **Fuzzy Ogrenci Eslestirme** — Farkli formatlardaki ayni ogrenciyi otomatik eslestirir (orn. "MIRAC AKYUZ" = "AKYUZ MIRAC")
- **6 Ders Takibi** — Turkce, Ink.Tar./Sos, Din Kulturu, Ingilizce, Matematik, Fen Bilimleri
- **Dogru/Yanlis/Net** detayli skor takibi
- **Grafik Raporlar** — Ogrenci trend grafigi, sinif karsilastirmasi, net dagilimi
- **CSV/Excel Export** — Verileri disa aktarma

## Kullanim

1. **PDF Yukle** — Sol menuden "📄 PDF Yukle" secin
2. **Parser Secin** — "Otomatik Algila" genellikle yeterlidir
3. **Analiz Et** — PDF'i yukleyip "🔍 PDF'i Analiz Et" butonuna basin
4. **Kaydet** — Onizlemeden sonra "💾 Veritabanina Kaydet"
5. **Incele** — "👤 Ogrenci Takibi" veya "📈 Grafik Raporlar" sayfalarini kullanin

## Desteklenen Formatlar

| Format | Parser | Aciklama |
|--------|--------|----------|
| MOBESE | `MobeseParser` | MOBESE sinav sonuc PDF'leri (30+ sutun) |
| SORUNET/LGS | `SorunetParser` | METIN/SORUNET LGS deneme sinavi PDF'leri (33 sutun) |
| Genel | `GenericParser` | Bilinmeyen formatlar icin heuristic parser |

## Kurulum (Yerel)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Teknolojiler

- **Streamlit** — Web arayuzu
- **pdfplumber** — PDF tablo cikarma
- **SQLite** — Veritabani
- **Plotly** — Grafikler
- **pandas** — Veri isleme
