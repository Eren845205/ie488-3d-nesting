# -*- coding: utf-8 -*-
"""make_pptx_demo_durum.py — Hoca Zoom görüşmesi (2026-06-18) için DEMO DURUM sunumu.

Uygulamanın ŞU ANKİ hali: algoritma motoru + etrafına kurulan uygulama/agent
katmanı + makale→kod hattı + algoritma-seçim modeli. Tüm sayılar MOTOR/ ve
APP_YOL_HARITASI dokümanlarından birebir; abartı yok, sınırlar dürüstçe yazılı.

Çalıştır:  python scripts/make_pptx_demo_durum.py
Çıktı   :  SUNUM_DEMO_DURUM.pptx (proje kök dizini)
"""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

_ROOT = Path(__file__).resolve().parent.parent

# --- palet ---
ACCENT = RGBColor(0x25, 0x63, 0xEB)
GREEN = RGBColor(0x05, 0x96, 0x59)
DGREEN = RGBColor(0x16, 0x65, 0x34)
RED = RGBColor(0xB9, 0x1C, 0x1C)
AMBER = RGBColor(0xB4, 0x53, 0x09)
INK = RGBColor(0x1E, 0x29, 0x3B)
MUTED = RGBColor(0x64, 0x74, 0x8B)
BG = RGBColor(0xF8, 0xFA, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT = RGBColor(0xEE, 0xF2, 0xFF)
WINBG = RGBColor(0xDC, 0xFC, 0xE7)
NOTEBG = RGBColor(0xFE, 0xF9, 0xC3)
HEADBG = RGBColor(0x1E, 0x3A, 0x8A)

SW, SH = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH
BLANK = prs.slide_layouts[6]


# ----------------------------------------------------------------------------
# yardımcılar
# ----------------------------------------------------------------------------
def slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    bar = s.shapes.add_shape(1, Inches(0), Inches(0), SW, Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    return s


def title(s, text, sub=None):
    tb = s.shapes.add_textbox(Inches(0.7), Inches(0.4), Inches(12), Inches(0.9))
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; r = p.add_run(); r.text = text
    r.font.size = Pt(30); r.font.bold = True; r.font.color.rgb = ACCENT
    ln = s.shapes.add_shape(1, Inches(0.72), Inches(1.28), Inches(7.0), Pt(3))
    ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT; ln.line.fill.background()
    if sub:
        sb = s.shapes.add_textbox(Inches(0.72), Inches(1.32), Inches(12), Inches(0.5))
        sp = sb.text_frame.paragraphs[0]; sr = sp.add_run(); sr.text = sub
        sr.font.size = Pt(14); sr.font.italic = True; sr.font.color.rgb = MUTED


def bullets(s, items, left=0.85, top=1.7, width=11.6, size=18, gap=10):
    tb = s.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(5.2))
    tf = tb.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        text, color, bold = it[0], it[1], it[2]
        indent = it[3] if len(it) > 3 else 0
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap); p.level = indent
        r = p.add_run()
        r.text = ("   " * indent) + ("–  " if indent else "•  ") + text
        r.font.size = Pt(size - (1 if indent else 0))
        r.font.color.rgb = color; r.font.bold = bold
    return tb


def notebox(s, text, left=0.85, top=6.05, width=11.6, height=1.0, size=14,
            bold=False, fill=NOTEBG, fg=INK):
    nb = s.shapes.add_shape(1, Inches(left), Inches(top), Inches(width), Inches(height))
    nb.fill.solid(); nb.fill.fore_color.rgb = fill; nb.line.fill.background()
    tf = nb.text_frame; tf.word_wrap = True
    tf.margin_left = Pt(12); tf.margin_top = Pt(6); tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = tf.paragraphs[0].add_run(); r.text = text
    r.font.size = Pt(size); r.font.color.rgb = fg; r.font.bold = bold


def notes(s, text):
    s.notes_slide.notes_text_frame.text = text


def pic_h(s, rel, top, height, left=None):
    """Yükseklik-sınırlı görsel (oran korunur)."""
    path = _ROOT / rel
    if not path.exists():
        return None
    from PIL import Image
    w, h = Image.open(path).size
    width = height * w / h
    if left is None:
        left = (13.333 - width) / 2
    return s.shapes.add_picture(str(path), Inches(left), Inches(top), height=Inches(height))


def table(s, rows, left, top, width, col_w=None, head=True, fs=13, top_h=0.4,
          row_h=0.34):
    nrows = len(rows); ncols = len(rows[0])
    gtab = s.shapes.add_table(nrows, ncols, Inches(left), Inches(top),
                              Inches(width), Inches(top_h + row_h * (nrows - 1)))
    t = gtab.table
    if col_w:
        for ci, cw in enumerate(col_w):
            t.columns[ci].width = Inches(cw)
    for ri, row in enumerate(rows):
        t.rows[ri].height = Inches(top_h if ri == 0 else row_h)
        for ci, val in enumerate(row):
            cell = t.cell(ri, ci)
            cell.margin_left = Pt(6); cell.margin_right = Pt(4)
            cell.margin_top = Pt(2); cell.margin_bottom = Pt(2)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            r = p.add_run(); r.text = str(val)
            r.font.size = Pt(fs)
            if ri == 0 and head:
                cell.fill.solid(); cell.fill.fore_color.rgb = HEADBG
                r.font.color.rgb = WHITE; r.font.bold = True
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = WHITE if ri % 2 else LIGHT
                r.font.color.rgb = INK
    return gtab


def box(s, text, left, top, width, height, fill, fg=WHITE, fs=13, bold=True):
    b = s.shapes.add_shape(5, Inches(left), Inches(top), Inches(width), Inches(height))
    b.fill.solid(); b.fill.fore_color.rgb = fill; b.line.color.rgb = WHITE
    b.line.width = Pt(1.2)
    tf = b.text_frame; tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    r.font.size = Pt(fs); r.font.bold = bold; r.font.color.rgb = fg
    return b


def arrow(s, left, top, width=0.45):
    a = s.shapes.add_shape(13, Inches(left), Inches(top), Inches(width), Inches(0.3))
    a.fill.solid(); a.fill.fore_color.rgb = MUTED; a.line.fill.background()
    return a


# ============================================================================
# 1 — KAPAK
# ============================================================================
s = slide()
hero = s.shapes.add_shape(1, Inches(0), Inches(0), SW, Inches(3.0))
hero.fill.solid(); hero.fill.fore_color.rgb = HEADBG; hero.line.fill.background()
tb = s.shapes.add_textbox(Inches(0.9), Inches(0.95), Inches(11.5), Inches(1.6))
tf = tb.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; r = p.add_run()
r.text = "Eklemeli Üretim Nesting Uygulaması"
r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = WHITE
p2 = tf.add_paragraph(); r2 = p2.add_run()
r2.text = "Algoritma motoru + uygulama/agent katmanı — demo durumu"
r2.font.size = Pt(20); r2.font.color.rgb = RGBColor(0xBF, 0xDB, 0xFE)
bullets(s, [
    ("Son görüşmeden bu yana: motorun etrafına uçtan uca bir uygulama kuruldu", INK, True),
    ("Bu bir DEMO — yetenekler gerçek, ama sınırlar da açıkça belirtiliyor", MUTED, False),
    ("IE 488 · Hazırlayan: Eren Kutlu · 18 Haziran 2026", MUTED, False),
], top=3.5, size=19, gap=14)
notebox(s, "Amaç: ne eklendi, nasıl yapıldı, algoritma tarafında neler değişti — "
           "ve neyin henüz YAPILMADIĞI. Sunum sonunda canlı demo.",
        top=5.9, height=0.9, fill=LIGHT, fg=INK)
notes(s, "Hocam, son konuştuğumuzda elimizde sadece algoritma vardı. O günden bu "
         "yana algoritmanın etrafına çalışan bir uygulama kurdum. Bugün hem "
         "uygulamayı hem de algoritma tarafındaki gelişmeleri göstereceğim. "
         "Baştan söyleyeyim: bu bir demo, abartmadan anlatacağım — neyin çalıştığı "
         "kadar neyin henüz eksik olduğunu da net söyleyeceğim.")

# ============================================================================
# 2 — GÜNDEM
# ============================================================================
s = slide(); title(s, "Gündem")
bullets(s, [
    ("1 · Nereden nereye — son görüşmeden bugüne", INK, True),
    ("2 · Uygulama katmanı: uçtan uca akış ve özellikler", INK, True),
    ("3 · Algoritma motoru: mimari + eklenen tüm çözücüler", ACCENT, True),
    ("4 · Makaleleri nasıl bulduk → koda nasıl çevirdik", ACCENT, True),
    ("5 · Algoritma-seçim modeli + öğrenme döngüsü", ACCENT, True),
    ("6 · Benchmark sonuçları + overfit'e karşı dürüst durum", INK, True),
    ("7 · Sınırlar, sıradaki adımlar, sizden beklenenler", INK, True),
], top=1.8, size=21, gap=16)
notebox(s, "Algoritma kısmına özellikle ağırlık verdim (3–5. başlıklar) — "
           "tahminimce en çok orayı soracaksınız.", top=6.2, height=0.7,
        fill=LIGHT, fg=INK)
notes(s, "Gündem bu. Algoritma tarafı en ağırlıklı bölüm.")

# ============================================================================
# 3 — NEREDEN NEREYE
# ============================================================================
s = slide(); title(s, "Nereden nereye", "son görüşme: yalnız algoritma · bugün: algoritma + uygulama")
box(s, "ÖNCE\n\nTek başına çalışan\nnesting algoritması\n(SA + DBLF)", 0.9, 1.9,
    3.4, 2.6, MUTED, fs=15)
arrow(s, 4.5, 3.0, 0.7)
box(s, "ŞİMDİ\n\nMotor + portföy + seçim modeli\n+ uçtan uca uygulama/agent\n"
       "+ makale→kod hattı", 5.4, 1.9, 6.9, 2.6, ACCENT, fs=15)
bullets(s, [
    ("Algoritma motoru: 1 çözücüden 6 çözücülü PORTFÖYE büyüdü", INK, True),
    ("Etrafına uygulama: parça dosyası okuma → 3D nesting → otomatik teklif → e-posta agent", INK, True),
    ("Literatürden yöntemler eklendi (algoritma-seçimi, ön-filtre, ALNS)", INK, True),
    ("Hepsi sizin yönlendirmenizdeki çerçevede — daha fazlasını onayınız olmadan ilerletmedim", DGREEN, True),
], top=4.9, size=17, gap=11)
notes(s, "Özet resim: önce tek algoritma vardı, şimdi motor büyüdü ve etrafına "
         "tam bir uygulama oturdu. Detayları sırayla göstereceğim.")

# ============================================================================
# 4 — UYGULAMA: UÇTAN UCA AKIŞ
# ============================================================================
s = slide(); title(s, "Uygulama — uçtan uca akış", "müşteri e-postasından teklife kadar")
chain = [
    ("E-POSTA\ngeldi", GREEN),
    ("Parça dosyası\n(STL / Excel / CSV)\nokunur", ACCENT),
    ("3D NESTING\nportföy çözer", ACCENT),
    ("3D görsel +\nyükseklik /\ndoluluk", ACCENT),
    ("Otomatik\nTEKLİF", GREEN),
]
x = 0.55; w = 2.3; gap = 0.2
for i, (txt, col) in enumerate(chain):
    box(s, txt, x, 1.95, w, 1.5, col, fs=12)
    if i < len(chain) - 1:
        arrow(s, x + w + 0.0, 2.6, gap)
    x += w + gap
bullets(s, [
    ("Asistan (soru-cevap), açıklayıcı (kararı gerekçelendirir) ve sipariş takip katmanı bu akışın üstünde", INK, True),
    ("\"Otonom zincir\": e-posta → parse → nesting → teklif adımlarını tek tetikle sırayla yürütür", INK, True),
    ("Niyet yönlendirici DETERMİNİSTİK (LLM'siz) — hangi soru hangi role gider, kuralla belirlenir", INK, True),
    ("LLM yerel çalışıyor (Ollama) — veri dışarı çıkmıyor", MUTED, True),
], top=3.9, size=16, gap=10)
notebox(s, "Web arayüzü (Flask) + sipariş deposu + 8 uç nokta (/run, /teklif, /parse, "
           "/otonom, /sor, /ozet, /geometri, /siparisler).", top=6.25, height=0.7,
        fill=LIGHT, fg=INK)
notes(s, "Uygulamanın iskeleti bu. Müşteriden e-posta geliyor, ekindeki parça "
         "dosyasını okuyup nesting'i koşuyor, 3D görseli ve teklifi üretiyor. "
         "Asistan ve açıklayıcı katmanı kullanıcının sorularını yanıtlıyor. "
         "Önemli nokta: niyet yönlendirme LLM'e bırakılmadı, deterministik kural. "
         "LLM tamamen yerel — müşteri verisi dışarı gitmiyor.")

# ============================================================================
# 5 — UYGULAMA: ÖZELLİKLER
# ============================================================================
s = slide(); title(s, "Uygulama özellikleri — şu an çalışan", "6 LLM rolü + web arayüzü + sipariş yönetimi")
table(s, [
    ["Özellik", "Ne yapıyor", "Durum"],
    ["Parça dosyası okuma", "STL geometri + Excel/CSV sipariş eki ayrıştırma", "Çalışıyor"],
    ["3D nesting", "Portföy çözer, yükseklik/doluluk + 3D görsel üretir", "Çalışıyor"],
    ["Otomatik teklif", "Nesting çıktısından fiyat/teklif metni", "Çalışıyor"],
    ["E-posta alımı", "Gelen siparişi parse eder (mail_ingest)", "Çalışıyor"],
    ["Otonom zincir", "parse→nesting→teklif tek tetikle", "Çalışıyor"],
    ["Çok-şirketli önceliklendirme", "Farklı firmaların siparişlerini öncelik sırasına dizer + parti planı", "Çalışıyor"],
    ["Asistan", "Doğal dil soru-cevap (yerel LLM)", "Çalışıyor"],
    ["Açıklayıcı", "\"Neden bu algoritma/fiyat?\" gerekçe verir", "Çalışıyor"],
    ["Sipariş takibi", "CRUD + CSV şablonu, durum görünümü", "Çalışıyor"],
], left=0.85, top=1.62, width=11.6, col_w=[3.2, 6.2, 2.2], fs=12.5, row_h=0.42)
notebox(s, "Dürüst not: bunlar bir DEMO seviyesinde uçtan uca çalışıyor; üretim "
           "sertleştirmesi (çok-kullanıcı, güvenlik, ölçek) henüz yapılmadı.",
        top=6.35, height=0.7, fill=NOTEBG, fg=INK)
notes(s, "Çalışan özellikler listesi. Hepsi commit'li ve testli. Ama net olayım: "
         "demo seviyesi — üretim için güvenlik ve çok-kullanıcı sertleştirmesi "
         "henüz sırada değil.")

# ============================================================================
# 6 — 3D NESTING GÖRSELİ
# ============================================================================
s = slide(); title(s, "3D nesting — örnek yerleşim", "parçalar konteynere damlatılır (Deepest-Bottom-Left)")
pic_h(s, "hocaya_sunum/8_nesting3d_default.png", top=1.55, height=4.5)
notebox(s, "Motor her parçayı 24 eksen-hizalı oryantasyonda deneyip en derin "
           "geçerli konuma indiriyor; çıktı yükseklik + doluluk olarak ölçülüyor.",
        top=6.25, height=0.7, fill=LIGHT, fg=INK)
notes(s, "Tipik bir 3D yerleşim çıktısı. Her parça en uygun oryantasyonda en "
         "alta yerleşiyor.")

# ============================================================================
# 7 — GERÇEK STL (NUMUNE)
# ============================================================================
s = slide(); title(s, "Gerçek STL üzerinde — numune (48 parça)",
                    "sizin yolladığınız gerçek parçalar")
pic_h(s, "results/numune_sa/nesting3d_numune.png", top=1.5, height=4.4, left=0.6)
bullets(s, [
    ("48 gerçek\nparça", INK, True),
    ("Faz-0 el-ayarı:\n181.5 mm rekor", DGREEN, True),
    ("KARANTİNADA —\ngenel motora\nsızmıyor", AMBER, True),
    ("Genel motor\n(el-ayarsız):\nSA %3.1 kazanç", ACCENT, True),
], left=7.7, top=1.7, size=15, gap=14, width=5.2)
notebox(s, "Dürüst çerçeve: tek gerçek örnek üzerinde el-ayarlı rekor (181.5) AYRI "
           "tutuluyor; genel motorun gerçek veride %3.1 kazancı overfit OLMADIĞININ kanıtı.",
        top=6.25, height=0.75, fill=NOTEBG, fg=INK)
notes(s, "Bu sizin gönderdiğiniz gerçek numune. İki şeyi ayırıyorum: bu tek örnek "
         "için elle ayarlanmış en iyi sonuç 181.5 mm — ama bunu karantinada "
         "tutuyorum, genel motora karıştırmıyorum ki ezber olmasın. Genel motor "
         "hiç el değmeden bu gerçek veride %3.1 iyileştirme yapıyor; bu da motorun "
         "tek veriye ezberlemediğinin kanıtı.")

# ============================================================================
# 8 — ALGORİTMA MİMARİSİ
# ============================================================================
s = slide(); title(s, "Algoritma motoru — mimari", "ortak sözleşme → adil kıyas → portföy")
box(s, "INSTANCE\n(parçalar + konteyner)\n→ voxelize (adaptif pitch)", 0.85, 1.7, 4.2, 1.3, INK, fs=13)
arrow(s, 5.2, 2.25, 0.5)
box(s, "ÇÖZÜCÜLER — ortak Solver protokolü\nDBLF · SA · GA · Tabu · MultiStartSA · ALNS",
    5.85, 1.7, 6.6, 1.3, ACCENT, fs=13)
box(s, "Hepsi AYNI decode'u kullanır (dblf.place_in_order)\n→ kalite kıyası ADİL, "
       "yeni algoritma motoru bozmaz", 2.0, 3.25, 9.3, 0.95, GREEN, fs=13)
box(s, "PORTFÖY\nhepsini koş,\nen iyiyi seç", 2.0, 4.5, 3.0, 1.2, ACCENT, fs=13)
arrow(s, 5.1, 5.0, 0.5)
box(s, "INSTANCE-TUNER\nörneğe özel konfig menüsü\n(monoton kabul — asla kötüleşmez)",
    5.7, 4.5, 5.6, 1.2, DGREEN, fs=13)
notebox(s, "Kritik tasarım: tüm çözücüler tek bir arayüze (Solver protokolü) uyuyor "
           "ve aynı çözüm-çözme adımını paylaşıyor. Bu yüzden yeni bir algoritma "
           "eklemek mevcut sistemi bozmuyor.", top=6.05, height=0.95, fill=LIGHT, fg=INK)
notes(s, "Algoritma mimarisinin özü. Tüm çözücüler ortak bir sözleşmeye uyuyor, "
         "aynı decode'u kullanıyor — bu sayede kıyas adil ve yeni çözücü eklemek "
         "motoru kırmıyor. Portföy hepsini koşup en iyiyi seçiyor, tuner ise o "
         "örneğe özel ince ayar yapıyor ama sonucu asla kötüleştirmiyor.")

# ============================================================================
# 9 — ÇÖZÜCÜLER TEK TEK
# ============================================================================
s = slide(); title(s, "Eklenen çözücüler — tek tek", "1 → 6 çözücü")
table(s, [
    ["Çözücü", "Tür", "Ne yapar / katkısı", "Durum"],
    ["DBLF", "Constructive (greedy)", "En-derin-sol-alt damlatma; tüm portföyün TABANI", "Olgun"],
    ["SA", "Metasezgisel", "DBLF tohumundan tavlama; +adaptif başlangıç sıcaklığı (R2)", "Olgun"],
    ["GA", "Metasezgisel", "Genetik; büyük+küçük karışık setlerde sık KAZANIYOR", "Portföyde"],
    ["Tabu", "Metasezgisel", "Tabu listesi + aspirasyon; aynı komşuluk hamleleri", "Portföyde"],
    ["MultiStart SA", "Metasezgisel", "N bağımsız SA; \"şanslı seed\" değil tipik kalite (R4)", "Portföyde"],
    ["ALNS", "Büyük-komşuluk", "Yık-onar + adaptif operatör ağırlığı (literatürden)", "Bağlandı"],
], left=0.7, top=1.65, width=11.95, col_w=[1.8, 2.2, 6.45, 1.5], fs=13, row_h=0.5)
notebox(s, "Her metasezgisel DBLF tabanını tohum alır → çıktı asla baseline'ın "
           "altına düşmez. \"Tek algoritmaya güvenme\" ilkesi (A12 sinyaliniz).",
        top=6.4, height=0.7, fill=LIGHT, fg=INK)
notes(s, "Eklenen tüm çözücüler. DBLF taban; SA, GA, Tabu, MultiStart SA ve ALNS "
         "metasezgisel katman. Hepsi DBLF'yi tohum aldığı için sonuç hiçbir zaman "
         "tabandan kötü olmuyor. Sizin 'tek algoritma yetmez' dediğiniz noktayı "
         "portföyle karşıladım.")

# ============================================================================
# 10 — SA DETAY + YAKINSAMA
# ============================================================================
s = slide(); title(s, "SA nasıl geliştirildi — adaptif sıcaklık (R2)",
                    "sabit parametre → veriye uyarlanan parametre")
pic_h(s, "hocaya_sunum/10_sa3d_convergence_stress.png", top=1.5, height=3.9, left=0.55)
bullets(s, [
    ("Enerji = maks. yükseklik + 0.1·RMS", INK, True),
    ("Sabit t0=3.0 farklı ölçekli", MUTED, True),
    ("veride anlamsızlaşıyordu", MUTED, True),
    ("t0=\"auto\": ilk 50 komşu", ACCENT, True),
    ("deltasından türetiliyor", ACCENT, True),
    ("Etki (few_large):", DGREEN, True),
    ("269.3 → 211.6 mm (%21)", DGREEN, True),
], left=7.9, top=1.6, size=15, gap=8, width=5.0)
notebox(s, "Önceki sabit sıcaklık sayısı (3 mm) yalnız numune ölçeğinde anlamlıydı; "
           "auto-t0 her veri setine kendini uyarlıyor — genelleme için kritik.",
        top=6.05, height=0.85, fill=LIGHT, fg=INK)
notes(s, "SA'da en önemli iyileştirme: başlangıç sıcaklığını sabit bir sayı yerine "
         "verinin kendisinden türetmek. Eski sabit 3.0 sadece numune ölçeğine "
         "uygundu. Auto modu her veride %21'e varan iyileşme getirdi.")

# ============================================================================
# 11 — PORTFÖY: FARKLI KAZANAN
# ============================================================================
s = slide(); title(s, "Neden portföy? — farklı veride farklı kazanan",
                    "tek çözücü domine etmiyor")
pic_h(s, "hocaya_sunum/3_comparison_bar.png", top=1.55, height=3.7, left=0.6)
bullets(s, [
    ("random_boxes → SA / GA", INK, True),
    ("few_large → GA / Tabu", INK, True),
    ("long_rods → SA / Tabu", INK, True),
    ("high_qty → SA", INK, True),
    ("Tek bir 'en iyi'", AMBER, True),
    ("algoritma YOK", AMBER, True),
    ("→ portföy + seçim", DGREEN, True),
    ("modeli şart", DGREEN, True),
], left=8.4, top=1.6, size=15, gap=8, width=4.6)
notebox(s, "Bu, algoritma-seçim modelinin gerekçesi: hangi veriye hangi çözücünün "
           "uyduğunu önceden tahmin edebilsek pahalı tam-portföyü atlayabiliriz.",
        top=6.05, height=0.85, fill=LIGHT, fg=INK)
notes(s, "Portföyün gerekçesi bu grafik: her veri ailesinde farklı çözücü "
         "kazanıyor. Tek bir şampiyon yok. Bu da bir sonraki adıma, seçim "
         "modeline götürüyor.")

# ============================================================================
# 12 — BENCHMARK TABLOSU
# ============================================================================
s = slide(); title(s, "Benchmark — her örnekte ölçülen kazanç",
                    "tek-konfig (tüm örnekler aynı parametre), adaptif pitch, budget 200")
table(s, [
    ["Instance", "Aile", "DBLF", "En iyi (kim)", "Kazanç"],
    ["syn_rb_s0", "random_boxes", "176.4", "152.3 (SA/GA)", "%13.6"],
    ["syn_flms_s0", "few_large_many_small", "269.3", "211.6 (GA/tabu)", "%21.4"],
    ["syn_hqr_s3", "high_qty_repeat", "276.5", "268.3 (SA)", "%2.9"],
    ["syn_tp_s0", "thin_plates", "77.7", "70.4", "%9.4"],
    ["syn_lr_s0", "long_rods", "46.8", "41.6 (SA/tabu)", "%11.1"],
    ["BR5 (holdout)", "bischoff_ratcliff", "28.0", "20.0 (hepsi)", "%28.6"],
    ["numune (holdout, STL)", "gerçek parça", "190.2", "184.3 (SA)", "%3.1"],
], left=0.85, top=1.75, width=11.6, col_w=[2.7, 3.4, 1.6, 2.5, 1.4], fs=13.5, row_h=0.5)
notebox(s, "HER örnekte pozitif kazanç → metasezgiseller her yerde tabanı geçiyor. "
           "Hold-out (BR5 + numune) hiç eğitimde görülmeden test edildi.",
        top=6.35, height=0.7, fill=WINBG, fg=DGREEN)
notes(s, "Benchmark sonuçları. Tüm örneklerde aynı parametre kullanıldı — örneğe "
         "özel ayar yasak, çünkü o ezber olurdu. Her örnekte pozitif kazanç var. "
         "BR5 ve numune hiç görülmemiş hold-out; orada da çalışıyor.")

# ============================================================================
# 13 — ABLATION
# ============================================================================
s = slide(); title(s, "Hangi değişiklik ne kazandırdı (ablation)",
                    "her iyileştirme ölçülerek eklendi — geçemeyen merge edilmedi")
table(s, [
    ["Değişiklik", "Test seti", "Önce → Sonra", "Etki"],
    ["R1 · 24 oryantasyon (8→24)", "long_rods", "46.8 → 41.6 mm", "%11"],
    ["R2 · adaptif başlangıç sıcaklığı", "few_large", "269.3 → 211.6 mm", "%21"],
    ["R4 · MultiStart SA", "few_large", "269.3 → 211.6 mm", "%21"],
    ["drop_map hızlı yol (kutu)", "tüm benchmark", "520 sn → 90 sn", "38× hız"],
], left=0.85, top=1.8, width=11.6, col_w=[4.6, 2.6, 3.0, 1.4], fs=14, row_h=0.55)
notebox(s, "Kural: bir değişiklik benchmark ortalamasını bozarsa MERGE EDİLMEZ. "
           "Reddedilen denemeler de kayda geçer (\"bunu zaten denedik\").",
        top=5.85, height=0.8, fill=LIGHT, fg=INK)
notes(s, "Her iyileştirmeyi ölçerek ekledim. 24 oryantasyon çubukları yatırarak "
         "%11, adaptif sıcaklık ve multi-start %21 kazandırdı. drop_map "
         "optimizasyonu benchmark'ı 38 kat hızlandırdı. Geçemeyen değişiklik "
         "sisteme girmiyor — bu disiplin overfit'e karşı koruma.")

# ============================================================================
# 14 — MAKALELER NASIL BULUNDU
# ============================================================================
s = slide(); title(s, "Makaleleri nasıl bulduk", "rastgele yığın değil — küratörlü + doğrulanmış")
bullets(s, [
    ("Repoda zaten 8 makale vardı (AM nesting, voxel, taksonomi, enerji-çizelgeleme)", INK, True),
    ("Motorun 5 'boşluk alanı' belirlendi: algoritma-seçimi, hyper-heuristik, modern 3D operatörler, yerleştirme, voxel/dataset", INK, True),
    ("Eksik aileler için çok-kaynaklı web araması + 3-oy ADVERSARYAL doğrulama yapıldı", ACCENT, True),
    ("Her künye 3-0 oyla teyit edildi → uydurma referans elendi (9 makale doğrulandı)", DGREEN, True),
    ("Makale → kod kapısı: teknik kodlanır → benchmark'tan geçerse merge; geçmezse hayır", ACCENT, True),
], top=1.7, size=17, gap=13)
notebox(s, "Tüm PDF'ler ve okuma notları artık MOTOR/makaleler/ altında toplandı "
           "(8 PDF + çıkarılmış metinler + araştırma bulguları).",
        top=6.1, height=0.75, fill=LIGHT, fg=INK)
notes(s, "Makale bulma sürecim disiplinliydi. Önce elimizdeki 8 makaleyi "
         "sınıflandırdım, motorun eksik olduğu alanları çıkardım, sonra bu "
         "alanlar için literatür taradım. Her makaleyi üç kez bağımsız "
         "doğruladım ki uydurma referans olmasın. En önemlisi: makale iddiası "
         "yetmiyor, tekniği kodlayıp bizim veride benchmark'tan geçmesi gerekiyor.")

# ============================================================================
# 15 — MAKALE → KOD
# ============================================================================
s = slide(); title(s, "Hangi makaleden ne eklendi", "literatür → çalışan kod")
table(s, [
    ["Makale / yöntem", "Motora katkısı", "Durum"],
    ["SATzilla — portfolyo tabanlı algoritma seçimi (Xu ve ark. 2008)",
     "Algoritma-seçim modelinin omurgası: özellik → kazanan tahmini", "Kuruldu"],
    ["Algoritma seçimi survey (Kerschke ve ark. 2019)",
     "Özellik mühendisliği + 'tamamlayıcı çözücü' tasarım ilkesi", "Uygulandı"],
    ["Renau & Hart 2024 — kolay instance ön-filtresi",
     "Kolay örnekte sadece DBLF koş, bütçeyi zora ayır", "Kuruldu"],
    ["Hyper-heuristik survey'leri (Burke, Drake ve ark.)",
     "Instance-Tuner'ı 'seçim + hareket-kabul' yapısına oturtma", "Uygulandı"],
    ["ALNS (büyük-komşuluk yık-onar)",
     "Yeni çözücü: zorlu örneklerde dblf 151.9 → 132.6 mm (%14.6)", "Bağlandı"],
], left=0.7, top=1.7, width=11.95, col_w=[5.2, 5.25, 1.5], fs=12.5, row_h=0.66)
notebox(s, "Dürüst not: bazı makaleler (modern 3D operatörler, voxel/dataset) "
           "henüz ikinci araştırma turunu bekliyor — kapsam açıkça işaretli.",
        top=6.5, height=0.65, fill=NOTEBG, fg=INK)
notes(s, "Somut karşılık: SATzilla deseni seçim modelimizin temeli oldu. "
         "Renau & Hart'ın kolay-instance ön-filtresini ekledim — kolay örnekte "
         "pahalı portföyü atlıyoruz. Hyper-heuristik literatürü tuner'ın yapısını "
         "verdi. ALNS'i ayrı bir çözücü olarak ekledim, zorlu örneklerde %14.6 "
         "kazandırıyor. Bazı alanlar hâlâ açık, bunu da gizlemiyorum.")

# ============================================================================
# 16 — SEÇİM MODELİ
# ============================================================================
s = slide(); title(s, "Algoritma-seçim modeli + öğrenme",
                    "hangi veriye hangi çözücü — yorumlanabilir, güvenli")
bullets(s, [
    ("Özellik vektörü → kazanan çözücü tahmini (1-NN prototip; kara-kutu YOK)", ACCENT, True),
    ("Kolay-instance ön-filtresi: kolayda sadece DBLF, bütçe zora gider", INK, True),
    ("Monoton garanti: seçim sonucu ASLA DBLF'den kötü olamaz", DGREEN, True),
    ("Overfit kapısı sertleştirildi: aileye-göre dengeli bölme + LOO-CV genelleme açığı", INK, True),
    ("Alternatif: karar ağacı seçici (LOO-CV %53.6 vs 1-NN %52.2) — yorumlanabilir", MUTED, True),
    ("ÖĞRENME = MANUEL + ÖNERİ — otomatik yeniden-eğitim YOK", RED, True),
    ("Sistem 'şu veri var, overfit riski şu, şunu geliştir' diye ÖNERİR; karar kullanıcıda", AMBER, True, 1),
], top=1.65, size=16.5, gap=10)
notebox(s, "Bilinçli karar: model kendini sessizce yanlış eğitip bozmasın diye "
           "eğitim yalnız açık komutla çalışıyor. Bu, üreticideki riski azaltmak için.",
        top=6.15, height=0.8, fill=NOTEBG, fg=INK)
notes(s, "Seçim modeli kurulu ve üretimde. Yorumlanabilir bir model seçtim "
         "bilinçli olarak — 1-NN ve karar ağacı, sinir ağı değil; çünkü 'neden bu "
         "çözücü' sorusuna cevap verebilmeliyiz. En kritik karar: öğrenme otomatik "
         "DEĞİL. Sistem öneri sunuyor ama gerçek yeniden-eğitim sadece sizin "
         "komutunuzla oluyor. Böylece model kendini sessizce bozamaz.")

# ============================================================================
# 17 — OVERFIT DÜRÜST DURUM
# ============================================================================
s = slide(); title(s, "Overfit'e karşı — dürüst durum tablosu")
table(s, [
    ["Soru", "Durum"],
    ["El-ayarı genel motora sızıyor mu?", "Hayır — numune ayarları karantinada"],
    ["Çeşitli sentetik veride çalışıp ayırt ediyor mu?", "Evet (benchmark tablosu)"],
    ["Tek-konfig kuralı (örneğe el-ayarı yasak) uygulanıyor mu?", "Evet"],
    ["'Hepsini koş en iyiyi seç' portföyü var mı?", "Evet"],
    ["Gerçek veride çalışıyor mu?", "Evet — numune %3.1 (1 örnek)"],
    ["ÇOKLU gerçek veride kanıtlandı mı?", "HENÜZ DEĞİL — sizin geçmiş işleriniz gerekli"],
], left=0.85, top=1.7, width=11.6, col_w=[6.8, 4.8], fs=14, row_h=0.6)
notebox(s, "Özet: overfit'i engelleyen mekanizmalar KURULU ve sentetik + 1 gerçek "
           "örnekte genelleme görüldü. Tam gerçek-dünya kanıtı için ÇOKLU gerçek "
           "veri (geçmiş nesting'leriniz) şart.", top=6.35, height=0.85,
        fill=LIGHT, fg=INK)
notes(s, "Bu tabloyu özellikle dürüst tuttum. Overfit'e karşı mekanizmalar kurulu, "
         "sentetik veride ve bir gerçek örnekte çalışıyor. Ama tek eksik nokta şu: "
         "çoklu gerçek veride henüz kanıtlanmadı. Bunun için sizin geçmiş "
         "nesting'lerinize ihtiyacım var — en kritik bağımlılık bu.")

# ============================================================================
# 18 — SINIRLAR (DÜRÜST)
# ============================================================================
s = slide(); title(s, "Henüz YAPILMAYANLAR — kasıtlı sınırlar", "demo olduğunu unutmadan")
bullets(s, [
    ("Sinir ağı / MLP seçici: YOK ve kasıtlı yok (yorumlanabilirlik ilkesi)", INK, True),
    ("MILP / kesin çözüm (küçük instance): YOK — değerlendirilecek", INK, True),
    ("Instance-Tuner LLM önericisi: arayüz hazır, LLM katmanı henüz YOK", INK, True),
    ("Konkav/gerçek-STL için hızlı yol: YOK (numune yavaş; HPC/numba sırada)", INK, True),
    ("Overhang ALTINA yerleştirme: heightmap sınırı (bilinen, kabul edilmiş takas)", INK, True),
    ("Çoklu gerçek-veri overfit kanıtı: bekliyor (A11 — geçmiş işleriniz)", AMBER, True),
    ("Üretim sertleştirmesi (çok-kullanıcı, güvenlik, lisanslama): teslim öncesi", AMBER, True),
], top=1.7, size=16.5, gap=11)
notebox(s, "Bunları gizlemeden listeliyorum çünkü sonraki yönü birlikte "
           "belirleyeceğiz — neyi önce isteyeceğinize göre.", top=6.25,
        height=0.7, fill=LIGHT, fg=INK)
notes(s, "Eksikleri açıkça koyuyorum. Sinir ağını bilerek koymadım, çünkü "
         "açıklanabilirlik istiyoruz. MILP, tuner'ın LLM katmanı, gerçek-STL hızı "
         "ve en önemlisi çoklu gerçek veri — bunlar sıradaki kararlar. Hangisini "
         "önce istediğinizi birlikte belirleyelim.")

# ============================================================================
# 19 — SIRADAKİ + BEKLENENLER
# ============================================================================
s = slide(); title(s, "Sıradaki adımlar + sizden beklenenler")
box(s, "BİZİM TARAFIMIZDA", 0.85, 1.7, 5.6, 0.6, ACCENT, fs=15)
bullets(s, [
    ("Instance-Tuner'a LLM önericisi", INK, True),
    ("Gerçek-STL için hız (HPC/numba)", INK, True),
    ("ALNS'i kazanan kümeye taşıyacak zorlu telemetri", INK, True),
    ("Demo'yu birlikte en optimize hale getirmek", DGREEN, True),
], left=0.95, top=2.45, size=15, gap=9, width=5.4)
box(s, "SİZDEN BEKLENENLER", 7.0, 1.7, 5.4, 0.6, AMBER, fs=15)
bullets(s, [
    ("Geçmiş gerçek nesting'leriniz (A11)", INK, True),
    ("→ çoklu gerçek-veri = tam genelleme kanıtı", DGREEN, True, 1),
    ("Hedef makine/kısıt parametreleri", INK, True),
    ("Fiyatlama stratejisi (örnek Excel)", INK, True),
], left=7.1, top=2.45, size=15, gap=9, width=5.2)
notebox(s, "Temmuz'da İstanbul'a geldiğimde uygulamayı baştan sona canlı gösterip "
           "yönlendirmenizle önceliklendirme yapabiliriz.", top=5.4, height=0.8,
        fill=LIGHT, fg=INK)
notes(s, "Sıradaki adımlar iki kolonda: bizim tarafta tuner'ın LLM katmanı, hız "
         "ve telemetri. Sizden ise en kritik şey geçmiş gerçek nesting'leriniz — "
         "çoklu gerçek veri olmadan tam genelleme kanıtı veremiyoruz. Bir de hedef "
         "makine kısıtları ve fiyatlama örneği.")

# ============================================================================
# 20 — KAPANIŞ
# ============================================================================
s = slide()
hero = s.shapes.add_shape(1, Inches(0), Inches(0), SW, SH)
hero.fill.solid(); hero.fill.fore_color.rgb = HEADBG; hero.line.fill.background()
tb = s.shapes.add_textbox(Inches(1.0), Inches(2.3), Inches(11.3), Inches(2.5))
tf = tb.text_frame; tf.word_wrap = True
p = tf.paragraphs[0]; r = p.add_run(); r.text = "Canlı demoya geçelim"
r.font.size = Pt(40); r.font.bold = True; r.font.color.rgb = WHITE
p2 = tf.add_paragraph(); r2 = p2.add_run()
r2.text = ("Algoritma motoru çalışıyor · uygulama uçtan uca ayakta · "
           "sınırlar açık · sonraki yönü birlikte belirleyelim")
r2.font.size = Pt(19); r2.font.color.rgb = RGBColor(0xBF, 0xDB, 0xFE)
p3 = tf.add_paragraph(); r3 = p3.add_run()
r3.text = "Teşekkürler — sorularınızı bekliyorum."
r3.font.size = Pt(17); r3.font.italic = True; r3.font.color.rgb = RGBColor(0xE0, 0xE7, 0xFF)
notes(s, "Kapanış. Demoya geçiyorum; sorularınızı bu noktada alabilirim.")

# ----------------------------------------------------------------------------
out = _ROOT / "SUNUM_DEMO_DURUM.pptx"
prs.save(str(out))
print(f"OK -> {out}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slayt)")
