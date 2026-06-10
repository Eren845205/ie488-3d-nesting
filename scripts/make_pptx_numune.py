"""make_pptx_numune.py — Numune fazı (gerçek parçalar) sonuç sunumu üretir.

make_pptx_3d.py görsel kalıbıyla aynı; içerik hocanın yolladığı 8 gerçek
numunenin (48 parça) yerleştirme sonuçları.  Konuşma metni her slaytın
PowerPoint "konuşmacı notları"na gömülüdür.

Çalıştır:  python scripts/make_pptx_numune.py
Çıktı   :  SUNUM_NUMUNE.pptx (proje kök dizini)

Gerekli görseller (önce üret — DEMO_NUMUNE.bat hepsini koşar):
  python -m src.nesting3d.run3d --scenario numune --algo dblf --voxel-method slice \
      --plate 350 --pitch 2.5 --export-stl --out results/numune_dblf
  python -m src.nesting3d.run3d --scenario numune --algo sa --iters 1000 \
      --voxel-method slice --plate 350 --pitch 2.5 --export-stl --out results/numune_sa
  python scripts/compare_numune.py
"""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

_ROOT = Path(__file__).resolve().parent.parent
_RES = _ROOT / "results"

ACCENT = RGBColor(0x25, 0x63, 0xEB)
GREEN = RGBColor(0x05, 0x96, 0x59)
RED = RGBColor(0xB9, 0x1C, 0x1C)
INK = RGBColor(0x1E, 0x29, 0x3B)
MUTED = RGBColor(0x64, 0x74, 0x8B)
BG = RGBColor(0xF8, 0xFA, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xEE, 0xF2, 0xFF)
WINBG = RGBColor(0xDC, 0xFC, 0xE7)
NOTEBG = RGBColor(0xFE, 0xF9, 0xC3)

# --- bu koşunun NET rakamları (results/numune_*/summary_3d.csv) ---
PARTS = 48
PLATE = "350×350 mm"
PITCH = "2.5 mm"
DBLF_H, DBLF_D = "180.0 mm", "0.102"
SA_H, SA_D = "155.0 mm", "0.118"
GAIN = "−25.0 mm  (%13.9)"
HOCA_REF = "170 mm"           # hocanın sözlü referansı — koşul teyidi gerekli
VS_HOCA = "−15.0 mm  (%8.8)"
SA_TIME = "506 s (1000 iterasyon)"

SW, SH = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH
BLANK = prs.slide_layouts[6]


def _bg(slide, color=BG):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _accent_bar(slide):
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), SW, Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()


def _title(slide, text):
    tb = slide.shapes.add_textbox(Inches(0.7), Inches(0.45), Inches(12), Inches(1.0))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; r = p.add_run(); r.text = text
    r.font.size = Pt(32); r.font.bold = True; r.font.color.rgb = ACCENT
    ln = slide.shapes.add_shape(1, Inches(0.72), Inches(1.45), Inches(7.5), Pt(3))
    ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT; ln.line.fill.background()


def _bullets(slide, items, left=0.8, top=1.85, width=11.7, size=20):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(5))
    tf = tb.text_frame; tf.word_wrap = True
    for i, (text, color, bold) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(12)
        r = p.add_run(); r.text = "•  " + text
        r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
    return tb


def _notebox(slide, text, left=0.8, top=5.5, width=11.7, height=1.2, size=16,
             bold=False):
    nb = slide.shapes.add_shape(1, Inches(left), Inches(top), Inches(width),
                                Inches(height))
    nb.fill.solid(); nb.fill.fore_color.rgb = NOTEBG; nb.line.fill.background()
    ntf = nb.text_frame; ntf.word_wrap = True
    ntf.margin_left = Pt(12); ntf.margin_top = Pt(8)
    nr = ntf.paragraphs[0].add_run()
    nr.text = text
    nr.font.size = Pt(size); nr.font.color.rgb = INK; nr.font.bold = bold


def _notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def _pic_center(slide, path, top=1.7, width=10.0):
    if not path.exists():
        return
    left = Inches((13.333 - width) / 2)
    slide.shapes.add_picture(str(path), left, Inches(top), width=Inches(width))


def _pic_center_h(slide, path, top, height):
    """Yükseklik-sınırlı ortalanmış görsel — slayt/notebox taşmasını önler."""
    if not path.exists():
        return
    from PIL import Image
    w, h = Image.open(path).size
    width = height * w / h
    left = Inches((13.333 - width) / 2)
    slide.shapes.add_picture(str(path), left, Inches(top), height=Inches(height))


def _caption(slide, text, left, top, width=6.5):
    cap = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width),
                                   Inches(0.5))
    cr = cap.text_frame.paragraphs[0].add_run()
    cr.text = text
    cr.font.size = Pt(12); cr.font.color.rgb = MUTED


def _metric_panel(slide, rows, left=8.2, top=1.9, width=4.6):
    """Sağ panel: büyük, net rakamlar (etiket + değer çiftleri)."""
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width),
                                  Inches(4.2))
    tf = tb.text_frame; tf.word_wrap = True
    first = True
    for label, value, color, big in rows:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(2)
        r = p.add_run(); r.text = label
        r.font.size = Pt(15); r.font.color.rgb = MUTED
        p2 = tf.add_paragraph(); p2.space_after = Pt(14)
        r2 = p2.add_run(); r2.text = value
        r2.font.size = Pt(34 if big else 24); r2.font.bold = True
        r2.font.color.rgb = color
    return tb


# ---------------------------------------------------------------- 1. Başlık
s = prs.slides.add_slide(BLANK); _bg(s)
box = s.shapes.add_shape(1, Inches(0.7), Inches(0.9), Inches(5.6), Inches(0.55))
box.fill.solid(); box.fill.fore_color.rgb = LIGHT; box.line.fill.background()
btf = box.text_frame; btf.margin_top = Pt(2); btf.margin_bottom = Pt(2)
bp = btf.paragraphs[0]; br = bp.add_run()
br.text = "IE 488 — Dönem Projesi · Numune Fazı (Gerçek Parçalar)"
br.font.size = Pt(16); br.font.bold = True; br.font.color.rgb = ACCENT
bp.alignment = PP_ALIGN.CENTER

tb = s.shapes.add_textbox(Inches(0.7), Inches(1.7), Inches(12), Inches(1.6))
tf = tb.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; r = p.add_run()
r.text = "Gerçek Numunelerle 3B Nesting — Sonuç Raporu"
r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = INK

# büyük sonuç bandı
band = s.shapes.add_shape(1, Inches(0.7), Inches(3.3), Inches(12), Inches(1.7))
band.fill.solid(); band.fill.fore_color.rgb = WINBG; band.line.fill.background()
btf2 = band.text_frame; btf2.word_wrap = True
btf2.margin_left = Pt(20); btf2.margin_top = Pt(10)
bp1 = btf2.paragraphs[0]
br1 = bp1.add_run(); br1.text = f"Z yüksekliği:  {DBLF_H}  →  {SA_H}"
br1.font.size = Pt(34); br1.font.bold = True
br1.font.color.rgb = RGBColor(0x16, 0x65, 0x34)
bp2 = btf2.add_paragraph()
br2 = bp2.add_run()
br2.text = f"SA kazancı {GAIN}   ·   density {DBLF_D} → {SA_D}   ·   referans: hocanın en iyisi {HOCA_REF}"
br2.font.size = Pt(18); br2.font.color.rgb = INK

tb2 = s.shapes.add_textbox(Inches(0.7), Inches(5.4), Inches(12), Inches(1.4))
tf2 = tb2.text_frame; tf2.word_wrap = True
p2 = tf2.paragraphs[0]; r2 = p2.add_run()
r2.text = (f"8 gerçek numune (Numuneler/1..8.stl) · toplam {PARTS} parça · "
           f"taban {PLATE} · voxel {PITCH}")
r2.font.size = Pt(18); r2.font.color.rgb = MUTED
p3 = tf2.add_paragraph(); p3.space_before = Pt(8)
r3 = p3.add_run()
r3.text = "STL → slice voxelization → DBLF baseline → Simulated Annealing → .STL"
r3.font.size = Pt(14); r3.font.color.rgb = MUTED
_notes(s,
"AÇILIŞ: 'Yolladığınız 8 numuneyi, verdiğiniz adetlerle (4/16/3/15/1/3/3/3 = 48 parça) "
"geliştirdiğimiz pipeline'dan geçirdim. Baseline 180 mm'ye istifledi; Simulated Annealing "
"bunu 155 mm'ye indirdi.'\n"
"170 mm KARŞILAŞTIRMASI: hocanın en iyisi 170 mm ise bizim 155 mm %8.8 daha iyi — ama "
"önce koşulları teyit et: aynı tabla boyutu mu, parça arası boşluk var mıydı? "
"Teyitsiz 'geçtik' deme; 'aynı koşullardaysa 15 mm öndeyiz' de.")

# ------------------------------------------------- 2. Numune seti (görsel)
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Verilen Numuneler — 8 Model, 48 Parça")
_pic_center_h(s, _RES / "numune_overview.png", top=1.6, height=4.55)
_notebox(s,
         "Gerçek mm boyutları korunarak yüklendi (ölçekleme YOK). En kritik kısıt: "
         "4.stl tam 304.8 mm (12\") — 220 mm tabla hiçbir duruşta almıyor → taban "
         "350×350 mm seçildi. Adetler: 1×4 · 2×16 · 3×3 · 4×15 · 5×1 · 6×3 · 7×3 · 8×3.",
         top=6.3, height=1.0, size=13)
_notes(s,
"'Sekiz numunenin gerçek boyutları bunlar — en büyüğü 304.8 milimetrelik şerit, "
"üç tanesi de 230'a 180'lik delikli plakalar. Bu yüzden tabanı 350'ye 350 aldım; "
"sizin tablanız farklıysa tek parametreyle yeniden koşuyorum.'\n"
"SORULURSA (neden 350?): 304.8 mm'lik parça 220'ye sığmıyor; 350 hem onu hem "
"plakaları rahat alıyor. Tabla boyutu --plate parametresi, tek komutla değişir.")

# ------------------------------------------------- 3. Kurulum / yöntem özeti
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Kurulum — Aynı Pipeline, Gerçek Veri")
_bullets(s, [
    (f"Taban {PLATE} (140×140 hücre grid), voxel boyutu {PITCH}, "
     "4 eksen-hizalı duruş/parça, parça arası ek boşluk 0.", INK, False),
    ("Yeni: slice voxelization — yüksek üçgen sayılı gerçek STL'lerde (235 bine "
     "kadar üçgen) eski yöntem parça başına ~30 sn sürüyor ve ince plakaları "
     "~2.5 kat şişiriyordu; yenisi 0.2 sn ve hacim-doğru.", GREEN, True),
    ("Aşama 2'deki algoritmalar DEĞİŞMEDİ: DBLF baseline + SA katmanı aynen "
     "kullanıldı — pipeline'ın model-bağımsızlığının testi.", INK, False),
    ("Doğrulama: 77 birim testi (72 eski + 5 yeni numune testi) geçiyor; "
     "seed=42, tekrar-üretilebilir.", INK, False),
])
_notebox(s,
         "Voxel çözünürlüğü 2.5 mm → raporlanan yükseklikler 2.5 mm'lik katmanlara "
         "YUKARI yuvarlanmış muhafazakâr değerlerdir (gerçek geometrik tepe bir miktar altında).",
         top=5.7, height=1.1)
_notes(s,
"'Algoritma tarafında hiçbir şey değişmedi — değişen tek şey girdi: sentetik üç model "
"yerine sizin sekiz numuneniz. Tek teknik ekleme voxelization hızlandırması oldu; "
"gerçek STL'ler çok yoğun üçgenli olduğu için eski yöntem hem yavaştı hem ince "
"plakaları şişiriyordu.'\n"
"Bu slayt 'pipeline gerçek veriye dayandı mı' sorusunun cevabı: evet, dokunmadan.")

# ------------------------------------------------- 4. DBLF yerleşimi (görsel + rakam)
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Yerleşim 1 — DBLF Baseline")
img = _RES / "numune_dblf" / "nesting3d_numune.png"
if img.exists():
    s.shapes.add_picture(str(img), Inches(0.45), Inches(1.65), width=Inches(7.5))
_caption(s, "48 parçanın tamamı yerleşti — greedy kural, hacim-azalan sıra", 0.8, 6.9)
_metric_panel(s, [
    ("Z yüksekliği", DBLF_H, INK, True),
    ("Packing density", DBLF_D, INK, True),
    ("Süre", "1.3 s", MUTED, False),
])
_notebox(s,
         "Büyük plakalar (3/6/7/8) tabanı kaplıyor, küçük parçalar aralara doluyor — "
         "ama greedy, plaka istifleme SIRASINI optimize edemiyor.",
         left=8.2, top=5.0, width=4.6, height=1.7, size=14)
_notes(s,
"'Baseline bir saniyede 48 parçayı 180 milimetreye istifledi. Yerleşim mantıklı "
"görünüyor — plakalar altta, küçükler arada — ama sıralama kararları greedy: "
"hangi plakanın hangi katmana gideceği optimize edilmiyor.'\n"
"Density neden düşük (0.102)? Zarf hacmi tüm 350×350×180 prizması; plakalar arası "
"hava da sayılıyor. Bu metrik karşılaştırma için anlamlı, mutlak değer için değil.")

# ------------------------------------------------- 5. SA yerleşimi (görsel + rakam)
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Yerleşim 2 — Simulated Annealing")
img = _RES / "numune_sa" / "nesting3d_numune.png"
if img.exists():
    s.shapes.add_picture(str(img), Inches(0.45), Inches(1.65), width=Inches(7.5))
_caption(s, "Aynı 48 parça — SA'nın bulduğu sıra + duruş kombinasyonu", 0.8, 6.9)
_metric_panel(s, [
    ("Z yüksekliği", SA_H, RGBColor(0x16, 0x65, 0x34), True),
    ("Packing density", SA_D, RGBColor(0x16, 0x65, 0x34), True),
    ("Kazanç (DBLF'e göre)", GAIN, GREEN, False),
    ("Süre", SA_TIME, MUTED, False),
])
_notes(s,
"'SA aynı parçaları 155 milimetreye indirdi — 25 milimetre, yüzde 14 kazanç. "
"Bu, şimdiye kadarki en büyük SA kazancımız: sentetik setlerde 3-4 milimetreydi.'\n"
"NEDEN GERÇEK PARÇALARDA DAHA ÇOK KAZANIYOR? Büyük delikli plakaların istif sırası ve "
"duruşu çok kritik; greedy'nin erken hataları pahalı. SA sıra+duruş uzayında arama "
"yapınca bu hatalar düzeliyor — yani SA katmanı tam da gerçek veride değer üretiyor.")

# ------------------------------------------------- 6. Karşılaştırma (rakamlar net)
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Karşılaştırma — Rakamlar")
rows = [
    ["", "Z yüksekliği", "Density", "Süre", "Not"],
    ["DBLF baseline", DBLF_H, DBLF_D, "1.3 s", "greedy, hacim-azalan"],
    ["SA (1000 iter)", SA_H, SA_D, "506 s", "sıra + duruş araması"],
    ["Hoca referansı", HOCA_REF, "—", "—", "koşul teyidi gerekli"],
]
tbl = s.shapes.add_table(4, 5, Inches(0.8), Inches(1.85),
                         Inches(11.7), Inches(2.5)).table
widths = [2.6, 2.2, 1.7, 1.5, 3.7]
for c, w in enumerate(widths):
    tbl.columns[c].width = Inches(w)
for c in range(5):
    cell = tbl.cell(0, c)
    cell.fill.solid(); cell.fill.fore_color.rgb = ACCENT
    para = cell.text_frame.paragraphs[0]; run = para.add_run(); run.text = rows[0][c]
    run.font.size = Pt(16); run.font.bold = True; run.font.color.rgb = WHITE
    para.alignment = PP_ALIGN.CENTER
for ri in range(1, 4):
    win = (ri == 2)
    for c in range(5):
        cell = tbl.cell(ri, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = WINBG if win else WHITE
        para = cell.text_frame.paragraphs[0]; run = para.add_run(); run.text = rows[ri][c]
        run.font.size = Pt(16); run.font.bold = win or (c == 1)
        run.font.color.rgb = RGBColor(0x16, 0x65, 0x34) if win else INK
        para.alignment = PP_ALIGN.CENTER

band = s.shapes.add_shape(1, Inches(0.8), Inches(4.7), Inches(11.7), Inches(1.1))
band.fill.solid(); band.fill.fore_color.rgb = WINBG; band.line.fill.background()
btf = band.text_frame; btf.word_wrap = True
btf.margin_left = Pt(16); btf.margin_top = Pt(10)
bp = btf.paragraphs[0]
br = bp.add_run()
br.text = (f"SA vs DBLF: {GAIN}        ·        "
           f"SA vs hoca referansı ({HOCA_REF}): {VS_HOCA}")
br.font.size = Pt(22); br.font.bold = True
br.font.color.rgb = RGBColor(0x16, 0x65, 0x34)
_notebox(s,
         "Dürüst çerçeve: 170 mm referansının tabla boyutu / parça boşluğu / yöntem "
         "koşulları bilinmiyor — aynı koşullar teyit edilirse '15 mm daha iyi' iddiası kesinleşir. "
         "Bizim 155 mm voxel'e YUKARI yuvarlanmış üst sınırdır (gerçek tepe ≤ 155).",
         top=6.0, height=1.2, size=14)
_notes(s,
"'Tabloda üç satır var: baseline 180, SA 155, sizin söylediğiniz en iyi 170. "
"Aynı koşullarda konuşuyorsak SA çözümü 15 milimetre — yüzde 9 — daha alçak.'\n"
"MUTLAKA SOR: 170'i hangi tablada, parça arası boşlukla mı almıştınız? "
"Koşullar farklıysa aynı koşulları --plate/--margin parametreleriyle birebir kurup "
"yeniden koşabilirim — pipeline parametrik.\n"
"Voxel notu: bizim rakam yukarı yuvarlanmış; gerçek geometrik tepe 155'in de altında.")

# ------------------------------------------------- 7. Görsel karşılaştırma
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Karşılaştırma — Yerleşimler Yan Yana")
_pic_center_h(s, _RES / "numune_comparison.png", top=1.6, height=5.7)
_notes(s,
"'Solda baseline, sağda SA — aynı parçalar, aynı taban. Alttaki çubuklar iki metriği "
"özetliyor: yükseklik 180'den 155'e iniyor, density 0.102'den 0.118'e çıkıyor.'\n"
"Görselde fark nereden geliyor? SA, plaka istif sırasını ve bazı parçaların duruşunu "
"değiştirerek katman sayısını azaltıyor — tek büyük hamle değil, kombinasyon kazancı.")

# ------------------------------------------------- 8. Yakınsama
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "SA Yakınsaması — Kazanç Nereden Geldi?")
img = _RES / "numune_sa" / "sa3d_convergence_numune.png"
if img.exists():
    s.shapes.add_picture(str(img), Inches(0.55), Inches(1.8), width=Inches(7.6))
_caption(s, "Best-so-far yükseklik / iterasyon — kesikli çizgi DBLF baseline", 0.8, 6.3)
tb = s.shapes.add_textbox(Inches(8.4), Inches(2.0), Inches(4.4), Inches(4.2))
tf = tb.text_frame; tf.word_wrap = True
for i, (txt, c, b) in enumerate([
    ("180.0 → 155.0 mm", GREEN, True),
    ("Kazancın tamamı ilk ~60 iterasyonda — sonrası plato.", INK, False),
    ("Voxel dünyasında iyileşme katman katman gelir (2.5 mm'lik basamaklar).", INK, False),
    ("Pratik sonuç: ~50 iterasyonluk koşu (≈30 sn) aynı sonucu verirdi — "
     "süre/kalite ayarı elimizde.", INK, False),
]):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    p.space_after = Pt(12)
    r = p.add_run(); r.text = ("" if i == 0 else "•  ") + txt
    r.font.size = Pt(22 if i == 0 else 16); r.font.color.rgb = c; r.font.bold = b
_notes(s,
"'Dürüst okuma: bin iterasyon koştum ama kazancın tamamı ilk altmış iterasyonda geldi. "
"Yani pratik kullanımda yarım dakikalık koşu yetiyor.'\n"
"Bu dürüstlük güven kazandırır — 'bin iterasyon şarttı' demek yanlış olurdu. "
"Daha uzun arama/daha ince pitch denenebilir; plato bunun bu çözünürlükteki sınır "
"olduğunu düşündürüyor ama kanıtlamıyor.")

# ------------------------------------------------- 9. STL çıktısı + kullanım
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Çıktılar ve Kullanıma Hazırlık")
_bullets(s, [
    ("Çözüm gerçek geometriye geri yazılıyor: results/numune_sa/"
     "nesting3d_result_numune.stl — slicer'da/3D Viewer'da açılabilir.", GREEN, True),
    ("Tek tık tekrar: DEMO_NUMUNE.bat — eksik paketleri kurar, iki koşuyu + "
     "karşılaştırma raporunu üretir (~10 dk).", INK, False),
    ("Parametrik: tabla boyutu (--plate), voxel inceliği (--pitch), parça arası "
     "boşluk (--margin), iterasyon (--iters) komut satırından.", INK, False),
    ("Farklı parça setleri: Numuneler/ klasörüne STL koymak + adet yazmak yeterli.", INK, False),
    ("Kod git'te sürümlü; rapor tabloları results/numune_comparison.md + "
     "numune_parts.csv.", INK, False),
])
_notebox(s,
         "Hoca kullanacaksa ihtiyaç listesi: Python 3.13 + pip (kurulumu bat hallediyor). "
         "Gerçek tabla boyutu ve parça arası boşluk kuralı netleşirse aynı gün yeniden koşulur.",
         top=5.8, height=1.1)
_notes(s,
"'Sonuç sadece görsel değil — STL sahnesi baskıya gidebilecek formatta hazır. "
"Sistemi kullanmak isterseniz tek bat dosyası her şeyi koşuyor; tabla boyutunuzu ve "
"parça arası boşluk kuralınızı söylemeniz yeterli.'\n"
"Bu slayt 'hoca algoritmayı kullanmak istiyor' ihtimalinin cevabı: teslim edilebilir durumda.")

# ------------------------------------------------- 10. Özet
s = prs.slides.add_slide(BLANK); _bg(s); _accent_bar(s)
_title(s, "Özet")
_bullets(s, [
    (f"48 gerçek parçanın tamamı {PLATE} tabana yerleşti — pipeline gerçek "
     "veriyle, algoritmaya dokunmadan çalıştı.", INK, False),
    (f"Z yüksekliği: DBLF {DBLF_H} → SA {SA_H}  ({GAIN}).", GREEN, True),
    (f"Density: {DBLF_D} → {SA_D}.", GREEN, True),
    (f"Hoca referansı {HOCA_REF}'ye karşı {VS_HOCA} — koşul teyidiyle "
     "kesinleşecek.", INK, True),
    ("Tekrar-üretilebilir: seed=42 · 77 test · DEMO_NUMUNE.bat · STL çıktıları hazır.", INK, False),
])
qb = s.shapes.add_textbox(Inches(0.8), Inches(5.6), Inches(11.7), Inches(1))
qr = qb.text_frame.paragraphs[0].add_run()
qr.text = "Teşekkürler — 170 mm'nin koşullarını teyit edebilir miyiz?"
qr.font.size = Pt(24); qr.font.color.rgb = MUTED; qr.font.italic = True
_notes(s,
"KAPANIŞ: 'Yolladığınız numunelerin tamamını yerleştirdik: baseline 180, SA 155 milimetre. "
"Sizin 170 milimetrelik referansınızla aynı koşullardaysak 15 milimetre öndeyiz. "
"Koşulları teyit edelim; isterseniz sisteminize aynen kurabilirim.'\n"
"Tek soruyla bitir: 170'in tabla boyutu ve boşluk kuralı neydi?")

out = _ROOT / "SUNUM_NUMUNE.pptx"
prs.save(str(out))
print(f"Yazildi: {out}  ({len(prs.slides)} slayt)")
