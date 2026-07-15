/* sokum_konsol.js — Operator Sokum Konsolu (P3 renk + P4 tikla-tani + P5 rehber).
 *
 * viewer3d.js handle'i uzerine operator katmani: gecmis_detay + sonuc ayni
 * modulu kullanir (P6 parite). Veri = pipeline P0/P1 kayitlari:
 *   parca_kimlik  {part_id: {parca_uid, order_id, geo_imza, kaynak_ad, ad, kopya_no}}
 *   siparis_ozeti [{order_id, musteri, n_parca, n_sokum_planli}]
 *   sokum_sirasi  [part_id, ...]  (cikarma sirasi; kilitliler listede olmaz)
 *   sokum_plani   [{part_id, parca, eksen, aci_deg, yon, lift_vox}]
 * Kimlik ADA GUVENMEZ: tum join'ler part_id uzerinden (Eren ilkesi).
 * XSS hijyeni: siparis/musteri/parca adlari guvensiz veri -> yalniz
 * createElement + textContent (innerHTML YOK).
 */
import { SIPARIS_PALETI } from './viewer3d.js';

function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
}

function talimatMetni(planEntry) {
    if (!planEntry) return 'Duz cek — serbest yonden kaydirarak cikar.';
    const p = [];
    if ((planEntry.lift_vox | 0) > 0) p.push(`once ~${planEntry.lift_vox} mm yukari kaldir`);
    p.push(`${planEntry.eksen || '?'} ekseninde ${Math.round(planEntry.aci_deg || 0)}° dondur`);
    p.push(`${planEntry.yon || '?'} yonunden cek`);
    return p.join(', ') + '.';
}

export function kurSokumKonsolu({ bid, viewer, data, arac, panelKok }) {
    if (!viewer || !data || !data.parca_kimlik) return null;
    const kimlik = data.parca_kimlik;
    const ozet = data.siparis_ozeti || [];
    const sira = data.sokum_sirasi || [];
    const planByPid = new Map((data.sokum_plani || [])
        .filter(e => e.part_id).map(e => [e.part_id, e]));
    const musteriByOrder = new Map(ozet.map(o => [o.order_id, o.musteri]));

    let mod = 'tip';          // 'tip' | 'siparis' | 'rehber'
    let adim = 0;             // rehber adimi (0-index)
    let lejant = [];          // [{order_id, renk}]

    /* ---------------- arac cubugu (P3): renk modu + rehber butonu -------- */
    const bar = el('div', 'sk-bar');
    const modGrubu = el('div', 'sk-modlar');
    const btnTip = el('button', 'sk-btn sk-btn-mod is-aktif', 'Parca tipi');
    const btnSip = el('button', 'sk-btn sk-btn-mod', 'Siparis rengi');
    btnTip.type = btnSip.type = 'button';
    modGrubu.append(el('span', 'sk-etiket', 'RENK'), btnTip, btnSip);
    bar.appendChild(modGrubu);

    const lejantKutu = el('div', 'sk-lejant');
    bar.appendChild(lejantKutu);

    let btnRehber = null;
    if (sira.length) {
        btnRehber = el('button', 'sk-btn sk-btn-rehber', '▶ Rehberli sokum');
        btnRehber.type = 'button';
        bar.appendChild(btnRehber);
    }
    arac.appendChild(bar);

    function lejantCiz() {
        lejantKutu.replaceChildren();
        if (mod !== 'siparis') return;
        lejant.forEach(l => {
            const chip = el('span', 'sk-chip');
            const nokta = el('span', 'sk-chip-nokta');
            nokta.style.background = l.renk;
            chip.append(nokta, el('span', null,
                `${l.order_id}${musteriByOrder.get(l.order_id) ? ' · ' + musteriByOrder.get(l.order_id) : ''}`));
            lejantKutu.appendChild(chip);
        });
    }

    function modUygula(yeni) {
        mod = yeni;
        btnTip.classList.toggle('is-aktif', mod === 'tip');
        btnSip.classList.toggle('is-aktif', mod === 'siparis');
        if (mod === 'siparis') {
            lejant = viewer.siparisRengi(kimlik, SIPARIS_PALETI);
        } else if (mod === 'tip') {
            viewer.tipRengi();
        }
        lejantCiz();
    }
    btnTip.addEventListener('click', () => { rehberKapat(); modUygula('tip'); });
    btnSip.addEventListener('click', () => { rehberKapat(); modUygula('siparis'); });

    /* ---------------- tikla-tani paneli (P4) ----------------------------- */
    const panel = el('div', 'sk-panel');
    panel.style.display = 'none';
    panelKok.appendChild(panel);

    function panelGoster(partId) {
        panel.replaceChildren();
        if (!partId) { panel.style.display = 'none'; digerModuGeriYukle(); return; }
        const k = kimlik[partId];
        const baslik = el('div', 'sk-panel-baslik');
        baslik.append(el('span', 'sk-panel-ad', (k && k.ad) || partId));
        const kapat = el('button', 'sk-panel-kapat', '×');
        kapat.type = 'button';
        kapat.addEventListener('click', () => panelGoster(null));
        baslik.appendChild(kapat);
        panel.appendChild(baslik);

        const satir = (etiket, deger, mono) => {
            const r = el('div', 'sk-panel-satir');
            r.append(el('span', 'sk-panel-etiket', etiket),
                     el('span', 'sk-panel-deger' + (mono ? ' sk-mono' : ''), deger));
            panel.appendChild(r);
        };
        if (k) {
            satir('Kopya', `${k.kopya_no} / ${ozetParcaSayisi(k.order_id)}`);
            satir('Siparis', k.order_id || '-');
            if (musteriByOrder.get(k.order_id)) satir('Musteri', musteriByOrder.get(k.order_id));
            if (k.kaynak_ad && k.kaynak_ad !== k.ad) satir('Kaynak dosya', k.kaynak_ad, true);
            if (k.parca_uid) satir('Kimlik', k.parca_uid, true);
        } else {
            satir('Kimlik', 'kayit yok (eski kosu)');
        }
        const siraNo = sira.indexOf(partId);
        if (siraNo >= 0) satir('Sokum sirasi', `${siraNo + 1}. / ${sira.length}`);
        const talimat = el('div', 'sk-panel-talimat', talimatMetni(planByPid.get(partId)));
        if (planByPid.get(partId)) talimat.classList.add('sk-rot');
        panel.appendChild(talimat);
        panel.style.display = 'block';
        if (mod !== 'rehber') viewer.vurgula(partId);
    }

    function ozetParcaSayisi(orderId) {
        const o = ozet.find(x => x.order_id === orderId);
        return o ? o.n_parca : '?';
    }

    function digerModuGeriYukle() {
        if (mod === 'siparis') { lejant = viewer.siparisRengi(kimlik, SIPARIS_PALETI); }
        else if (mod === 'tip') viewer.tipRengi();
        // rehber modunda vurgu rehberde kalir
        if (mod === 'rehber') rehberCiz();
    }

    viewer.onPickHedef = pid => panelGoster(pid);

    /* ---------------- rehberli sokum HUD'u (P5) --------------------------- */
    const hud = el('div', 'sk-hud');
    hud.style.display = 'none';
    panelKok.appendChild(hud);

    const hudAdim = el('div', 'sk-hud-adim');
    const hudBilgi = el('div', 'sk-hud-bilgi');
    const hudTalimat = el('div', 'sk-hud-talimat');
    const hudBarDis = el('div', 'sk-hud-progress');
    const hudBarIc = el('div', 'sk-hud-progress-ic');
    hudBarDis.appendChild(hudBarIc);
    const hudKontrol = el('div', 'sk-hud-kontrol');
    const btnGeri = el('button', 'sk-btn', '← Geri');
    const btnIleri = el('button', 'sk-btn sk-btn-ileri', 'Ileri →');
    const btnCik = el('button', 'sk-btn sk-btn-cik', 'Bitir (ESC)');
    [btnGeri, btnIleri, btnCik].forEach(b => { b.type = 'button'; });
    hudKontrol.append(btnGeri, btnIleri, btnCik);
    hud.append(hudAdim, hudBilgi, hudTalimat, hudBarDis, hudKontrol);

    function rehberCiz() {
        const pid = sira[adim];
        const k = kimlik[pid];
        hudAdim.replaceChildren(
            el('span', 'sk-hud-no', String(adim + 1)),
            el('span', 'sk-hud-toplam', ` / ${sira.length}`));
        const parcaAd = (k && k.ad) || pid;
        const kutu = k && k.order_id
            ? `${k.order_id}${musteriByOrder.get(k.order_id) ? ' (' + musteriByOrder.get(k.order_id) + ')' : ''} kutusuna`
            : 'kutusuna';
        hudBilgi.replaceChildren(
            el('strong', null, parcaAd),
            el('span', null, k ? ` · kopya ${k.kopya_no} · ${kutu}` : ''));
        hudTalimat.textContent = talimatMetni(planByPid.get(pid));
        hudTalimat.classList.toggle('sk-rot', planByPid.has(pid));
        hudBarIc.style.width = `${((adim + 1) / sira.length) * 100}%`;
        btnGeri.disabled = adim === 0;
        btnIleri.textContent = adim === sira.length - 1 ? 'Tamamlandi ✓' : 'Ileri →';
        viewer.vurgula(pid);
    }

    function rehberAc() {
        if (!sira.length) return;
        mod = 'rehber';
        adim = 0;
        hud.style.display = 'flex';
        panel.style.display = 'none';
        if (btnRehber) btnRehber.classList.add('is-aktif');
        rehberCiz();
    }

    function rehberKapat() {
        if (mod !== 'rehber') return;
        hud.style.display = 'none';
        if (btnRehber) btnRehber.classList.remove('is-aktif');
        modUygula('tip');
    }

    if (btnRehber) btnRehber.addEventListener('click', () =>
        (mod === 'rehber' ? rehberKapat() : rehberAc()));
    btnIleri.addEventListener('click', () => {
        if (adim < sira.length - 1) { adim++; rehberCiz(); }
        else rehberKapat();
    });
    btnGeri.addEventListener('click', () => { if (adim > 0) { adim--; rehberCiz(); } });
    btnCik.addEventListener('click', rehberKapat);
    document.addEventListener('keydown', e => {
        if (mod !== 'rehber') return;
        if (e.key === 'Escape') rehberKapat();
        else if (e.key === 'ArrowRight') btnIleri.click();
        else if (e.key === 'ArrowLeft') btnGeri.click();
    });

    return { modUygula, rehberAc, rehberKapat, panelGoster };
}
