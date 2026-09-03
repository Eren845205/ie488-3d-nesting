# MOTOR — Algoritma Merkezi

> **Bu klasör motorun (genel motor + Instance-Tuner) ve TÜM algoritmaların tek
> kaynak-doğruluk merkezidir.** Algoritma üzerinde her değişiklikten ÖNCE buradaki
> son durum okunur; değişiklik bunun ÜSTÜNE eklenir; sonuçlar buraya işlenir.
> Amaç: motor gelişmeleri kalıcı, izlenebilir ve genişlemeye açık olsun.

## Neden ayrı merkez?

Motor (nesting algoritmaları) projenin **kalbi** ve ticari değerinin kaynağı.
Dağınık notlar yerine tek yerde toplanır ki: (1) "şu an ne var, ne kadar iyi"
bir bakışta görülsün; (2) yeni algoritma/makale **sistemi bozmadan** eklensin;
(3) hoca farklı bir şey isterse nereden devam edileceği belli olsun.

## İçindekiler

| Dosya | Ne var |
|---|---|
| [00_DEGISIKLIK_GUNLUGU.md](00_DEGISIKLIK_GUNLUGU.md) | **Karar kaydı:** ne eklendi/çıkarıldı/denendi-reddedildi, neden, benchmark etkisi (zaman çizelgesi). "Denedik, beğenmedik, çıkardık" buraya yazılır |
| [01_ALGORITMALAR.md](01_ALGORITMALAR.md) | Her algoritma ayrı ayrı: ne yapar, nerede (dosya), parametreler, güçlü/zayıf yön, durum |
| [02_PERFORMANS.md](02_PERFORMANS.md) | Veri seti başına benchmark sonuçları + EVRİM (nereden nereye getirildi) |
| [03_GENISLETME.md](03_GENISLETME.md) | Algoritma/makale EKLEME + ÇIKARMA/geri-alma sözleşmesi — sistemi bozmadan nasıl |
| [makaleler/00_OKUMA_LISTESI.md](makaleler/00_OKUMA_LISTESI.md) | Mevcut makaleler + araştırılacak makaleler + makale→kod hattı |

## 🥇 ALTIN KURAL — algoritma değişikliği yapmadan önce

1. **Son durumu oku:** ilgili algoritmayı `01_ALGORITMALAR.md`'de bul.
2. **Üstüne ekle, sıfırdan yazma:** mevcut yapı (`Solver` protokolü) korunur;
   yeni şey **eklenir** veya bir parametre/varyant olarak açılır.
3. **Benchmark kapısından geçir:** `python scripts/benchmark.py` — değişiklik
   benchmark ortalamasını bozuyorsa MERGE EDİLMEZ (tek-konfig kuralı, §5).
4. **Sonucu buraya işle:** `00_DEGISIKLIK_GUNLUGU.md`'ye bir satır (ne/neden/
   etki/durum) + 01 + 02 güncellenir; büyük değişiklik `APP_YOL_HARITASI.md`'ye
   de not düşülür. **Reddettiysen/geri aldıysan da yaz** (00'ın 🧪 bölümü) —
   "bunu zaten denedik" bilgisi tekrar çıkmaza girmeyi önler.

## İlgili kök dokümanlar

- `APP_YOL_HARITASI.md` — genel ürün yol haritası + motor overfit riskleri (§2 R1-R7)
- `PLAN_DEMO1.md` — Demo-1 fazlı plan (motor portföyü, benchmark)
- `PLAN_LLM.md` — LLM katmanı (Instance-Tuner LLM önericisi buraya bağlanır)

_Son güncelleme: 2026-06-14._
