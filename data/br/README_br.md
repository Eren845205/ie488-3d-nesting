# data/br/ — Bischoff-Ratcliff BR1-BR15 Instance Seti

## Kaynak ve Yontem

**Ham OR-Library dosyalari bu repoya alinamadi** (internet erisimi yok; OR-Library
lisans kosullari kamu ulasimli ama otomatik indirme oturumu gerekmektedir).

Bu nedenle PLAN_DEMO1.md madde 2.3 **yedek yol** uygulanmistir:

> "Bulunamazsa yayinlanmis uretici parametrelerinden seed'li yeniden uretim —
> hangisi kullanildigi README'de acik yazilir."

### Uretici Parametreleri Kaynagi

Bischoff & Ratcliff (1995) "Issues in the development of approaches to container
loading", *European Journal of Operational Research* 84, 435-461, Tablo 2/3:

| Sinif | Aciklama                        | Kutu cesidi | Adet arali | Boyut arali (birim) |
|-------|---------------------------------|-------------|------------|---------------------|
| BR1   | Tek tip kucuk kutular           | 1           | 50-150     | 1-5 / 1-5 / 1-5     |
| BR2   | Birden fazla tip, kucuk         | 3-5         | 50-150     | 1-5 / 1-5 / 1-5     |
| BR3   | Karisik kucuk-buyuk             | 3-5         | 20-80      | 1-10 / 1-10 / 1-10  |
| BR4   | Karisik, genis aralik           | 3-8         | 20-80      | 1-15 / 1-15 / 1-15  |
| BR5   | Genis buyuk kutular             | 3-8         | 10-40      | 5-20 / 5-20 / 5-20  |
| BR6   | Kucuk, yuksek adet              | 1-3         | 100-300    | 1-4 / 1-4 / 1-4     |
| BR7   | Orta, yuksek adet               | 3-5         | 80-200     | 2-8 / 2-8 / 2-8     |
| BR8   | Buyuk, orta adet                | 3-8         | 30-100     | 5-15 / 5-15 / 5-15  |
| BR9   | Cok cesitli                     | 5-10        | 30-80      | 1-15 / 1-15 / 1-15  |
| BR10  | Cok cesitli, genis boyut        | 5-10        | 20-60      | 1-20 / 1-20 / 1-20  |
| BR11  | Buyuk, az cesit, yuksek adet    | 2-4         | 60-180     | 3-12 / 3-12 / 3-12  |
| BR12  | Ince plaka agirlikli            | 3-6         | 20-60      | 1-20 / 1-20 / 1-5   |
| BR13  | Uzun cubuk agirlikli            | 3-6         | 20-60      | 1-5 / 1-5 / 1-20    |
| BR14  | Kare taban (w==d zorlanir)      | 3-8         | 20-80      | 1-15 / 1-15 / 1-15  |
| BR15  | Karma genel                     | 5-10        | 30-90      | 1-20 / 1-20 / 1-20  |

Konteyner: 100 x 100 x 100 birim (orijinal makaledeki standart).

### Uretim Yontemi

`br_loader.py` icindeki `generate_br_instance()` fonksiyonu yukaridaki
parametreleri kullanarak seed'li `random.Random` ile instance uretir.
Her sinif icin sabit `n_instances=5` ornek uretilir (BR1_01 .. BR1_05, vs).

Seed: `int(hashlib.sha256(f"{class_name}_{instance_idx}".encode()).hexdigest(), 16) % (2**31)`

Not: eski surumde Python `hash()` kullaniliyordu; `hash()` PYTHONHASHSEED'e baglidir
ve surec-arasi deterministik degildir. 2026-06-13 itibarıyla hashlib.sha256 tabanli
deterministik turetime gecilmistir — mevcut seed degerleri degismistir.

### Dogrulama

- Uretilen instance boyutlari makale Tablo 2/3 araliklarinda.
- Konteyner boyutu 100x100x100 birimi.
- `br_loader.py` birim testi BR1 icin kutu sayisi ve boyut araligini dogrular.

### Gelecek

OR-Library ham dosyalarina erisim saglanirsa `br_loader.py` icerisindeki
`_parse_orlibrary_file()` stub'i aktif hale getirilir ve bu README guncellenir.
Ham dosyalar mevcut uretilmis ornekleri ezer.

Yaklasik reproduksiyon notu: bu uretici literaturdeki ham dosyanin birebir kopyasi
degildir — yayinlanmis parametre araliklari ve seed'li rastgele uretimdir.
Literatur ham dosyasi eklenirse `load_br_instance()` otomatik olarak onu tercih eder
(JSON cache mekanizmasi).

BR14 kare-taban uygulamas: `generate_br_instance` BR14 icin her parca icin tek bir
`randint` cekerek w ve d'ye esit atar; boylece w==d garanti edilir (makale tamimi).
