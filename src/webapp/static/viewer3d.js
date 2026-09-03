/* viewer3d.js — ortak 3D yerlesim goruntuleyici (Sokum Konsolu P2).
 *
 * gecmis_detay.html + sonuc.html'deki KOPYA inline viewer'larin tek modulu.
 * Gelismis davranislar (instancing, agir-sahne modu, isik duzenegi, tam
 * ekran, lazy-init) korunur; ustune konsol API'leri gelir:
 *   - adlar: instanceId -> part_id haritasi (GLB dugum adlari `pid#0001`)
 *   - pick(cb): tikla-tani (Raycaster + instanceId)
 *   - siparisRengi(kimlik, palet) / tipRengi(): renk modlari
 *   - vurgula(partId) / soluklastir(partIdSet): rehberli sokum gorunumu
 *
 * ES module — sayfa importmap'inde 'three' tanimli olmali.
 */
import * as THREE from 'three';
import { OrbitControls } from './OrbitControls.js';
import { GLTFLoader } from './GLTFLoader.js';

const RENK_NOTR = new THREE.Color(0x3d4759);      // soluk (rehberli modda digerleri)
const RENK_VURGU = new THREE.Color(0xff7a2f);     // hedef parca (marka turuncusu)

/* Siparis paleti — koyu sahnede ayrisan, renk-koru dostu 12 ton
 * (mavi/amber/teal/magenta/yesil/mercan/mor/kum/cyan/gul/limon/lavanta) */
export const SIPARIS_PALETI = [
    0x4f9dde, 0xe8b931, 0x2fbf9b, 0xd964c0, 0x7bc95c, 0xe8704a,
    0x9d7de8, 0xc9a227, 0x3fc1d9, 0xe86a8a, 0xb5cc45, 0x8f9de0,
];

export function initViewer3d(opts) {
    const {
        container, canvas, placeholder, glbUrl,
        onReady = null, onPick = null,
    } = opts;
    if (!container || !canvas) return null;

    const handle = {
        hazir: false,
        renderer: null, camera: null, controls: null, scene: null,
        size: 0,
        gruplar: [],          // [{nesne, adlar[], geometry, material}]
        partIndex: new Map(), // part_id -> [{grup, i}]
        resize, vurgula, soluklastir, temizle, siparisRengi, tipRengi,
    };

    function sizeFor() {
        return { w: container.clientWidth || 600, h: container.clientHeight || 300 };
    }

    fetch(glbUrl)
        .then(resp => {
            if (!resp.ok) {
                if (placeholder) {
                    placeholder.textContent = '3D onizleme hazir degil';
                    placeholder.style.fontSize = '12px';
                }
                return null;
            }
            return resp.arrayBuffer();
        })
        .then(buffer => { if (buffer) kur(buffer); })
        .catch(() => {
            if (placeholder) placeholder.innerHTML =
                '<span style="color:#64748b; font-size:12px;">3D onizleme hazir degil</span>';
        });

    function kur(buffer) {
        if (placeholder) placeholder.style.display = 'none';
        canvas.style.display = 'block';
        const sz = sizeFor();

        // AGIR SAHNE modu: buyuk GLB = GPU fill yuku -> AA kapat, pixelRatio 1
        const agirSahne = buffer.byteLength > 12 * 1024 * 1024;
        const renderer = new THREE.WebGLRenderer({ canvas, antialias: !agirSahne });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, agirSahne ? 1 : 1.5));
        renderer.setSize(sz.w, sz.h);
        renderer.setClearColor(0x0f172a);

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, sz.w / sz.h, 1, 10000);
        camera.position.set(300, 300, 400);

        // Isik duzenegi: hemisphere + anahtar + dolgu (net yuzey okumasi)
        scene.add(new THREE.HemisphereLight(0xffffff, 0x3a4252, 0.9));
        const key = new THREE.DirectionalLight(0xffffff, 1.1);
        key.position.set(300, 500, 400);
        scene.add(key);
        const fill = new THREE.DirectionalLight(0xdde6ff, 0.45);
        fill.position.set(-350, 200, -300);
        scene.add(fill);

        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.screenSpacePanning = true;

        new GLTFLoader().parse(buffer, '', gltf => {
            const raw = gltf.scene;
            raw.updateMatrixWorld(true);

            // INSTANCING: ayni geometriye referans veren dugumleri tip basina
            // TEK InstancedMesh'e cevir; dugum ADLARI matrislere paralel
            // toplanir (instanceId -> part_id — konsolun kimlik iskeleti).
            const tipler = new Map(); // geometry.uuid -> {geometry, material, matrisler[], adlar[]}
            raw.traverse(child => {
                if (!child.isMesh) return;
                let mat = child.material;
                if (!mat || !mat.color) {
                    mat = new THREE.MeshLambertMaterial({ color: 0x4ade80 });
                }
                if (mat.isMeshStandardMaterial) {
                    mat.metalness = 0.0;
                    mat.roughness = 0.9;
                }
                mat.flatShading = true;
                mat.needsUpdate = true;
                if (child.geometry && !child.geometry.attributes.normal) {
                    child.geometry.computeVertexNormals();
                }
                let g = tipler.get(child.geometry.uuid);
                if (!g) {
                    g = { geometry: child.geometry, material: mat, matrisler: [], adlar: [] };
                    tipler.set(child.geometry.uuid, g);
                }
                g.matrisler.push(child.matrixWorld.clone());
                // GLB dugum adi `part_id#0001` — part_id'ye indir; ad yoksa null
                const ad = (child.name || '').split('#')[0] || null;
                g.adlar.push(ad);
            });

            const model = new THREE.Group();
            const box = new THREE.Box3();
            const kose = new THREE.Vector3();
            tipler.forEach(g => {
                g.geometry.computeBoundingBox();
                const gb = g.geometry.boundingBox;
                // Konsol renk API'leri icin HER tip InstancedMesh olur (tek
                // kopyali tipler dahil — setColorAt tek tip yolla calisir).
                const nesne = new THREE.InstancedMesh(g.geometry, g.material, g.matrisler.length);
                g.matrisler.forEach((m, i) => nesne.setMatrixAt(i, m));
                nesne.instanceMatrix.needsUpdate = true;
                model.add(nesne);
                const grup = { nesne, adlar: g.adlar, material: g.material };
                handle.gruplar.push(grup);
                g.adlar.forEach((ad, i) => {
                    if (!ad) return;
                    if (!handle.partIndex.has(ad)) handle.partIndex.set(ad, []);
                    handle.partIndex.get(ad).push({ grup, i });
                });
                g.matrisler.forEach(m => {
                    for (let ci = 0; ci < 8; ci++) {
                        kose.set(
                            (ci & 1) ? gb.max.x : gb.min.x,
                            (ci & 2) ? gb.max.y : gb.min.y,
                            (ci & 4) ? gb.max.z : gb.min.z,
                        ).applyMatrix4(m);
                        box.expandByPoint(kose);
                    }
                });
            });
            const center = box.getCenter(new THREE.Vector3());
            model.position.sub(center);
            scene.add(model);

            const size = box.getSize(new THREE.Vector3()).length();
            camera.position.set(size, size * 0.8, size * 1.2);
            camera.lookAt(0, 0, 0);
            controls.target.set(0, 0, 0);
            controls.update();

            Object.assign(handle, { renderer, camera, controls, scene, size, hazir: true });

            // --- Tikla-tani: Raycaster + instanceId -> part_id -------------
            // Dinleyici HER ZAMAN kurulur; hedef opsiyonel onPick + sonradan
            // atanabilir handle.onPickHedef (konsol viewer'dan sonra kurulur).
            {
                const ray = new THREE.Raycaster();
                const ndc = new THREE.Vector2();
                let downXY = null;
                canvas.addEventListener('pointerdown', e => { downXY = [e.clientX, e.clientY]; });
                canvas.addEventListener('pointerup', e => {
                    // Orbit suruklemesini tiklama sayma (5px esik)
                    if (!downXY) return;
                    const dx = e.clientX - downXY[0], dy = e.clientY - downXY[1];
                    downXY = null;
                    if (dx * dx + dy * dy > 25) return;
                    const r = canvas.getBoundingClientRect();
                    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1,
                            -((e.clientY - r.top) / r.height) * 2 + 1);
                    ray.setFromCamera(ndc, camera);
                    const hits = ray.intersectObjects(model.children, false);
                    let partId = null;
                    if (hits.length) {
                        const h = hits[0];
                        const grup = handle.gruplar.find(g => g.nesne === h.object);
                        const i = (h.instanceId !== undefined && h.instanceId !== null) ? h.instanceId : 0;
                        partId = grup ? (grup.adlar[i] || null) : null;
                    }
                    if (onPick) onPick(partId);
                    if (handle.onPickHedef) handle.onPickHedef(partId);
                });
            }

            (function animate() {
                requestAnimationFrame(animate);
                controls.update();
                renderer.render(scene, camera);
            })();

            if (onReady) onReady(handle);
        }, () => {
            if (placeholder) {
                placeholder.style.display = 'flex';
                canvas.style.display = 'none';
                placeholder.textContent = 'GLB parse hatasi';
                placeholder.style.color = '#ef4444';
                placeholder.style.fontSize = '12px';
            }
        });
    }

    // --- Renk / vurgu API'leri ---------------------------------------------
    // instanceColor kullanabilmek icin baked vertex-renkleri kapatilir;
    // tip moduna donuste geri acilir + instanceColor temizlenir.

    function _herInstance(fn) {
        handle.gruplar.forEach(grup => {
            const n = grup.nesne.count;
            for (let i = 0; i < n; i++) fn(grup, i);
        });
    }

    function _renkUygula(renkFn) {
        _herInstance((grup, i) => {
            grup.nesne.setColorAt(i, renkFn(grup.adlar[i], grup, i));
            grup.material.vertexColors = false;
            grup.material.needsUpdate = true;
        });
        handle.gruplar.forEach(g => {
            if (g.nesne.instanceColor) g.nesne.instanceColor.needsUpdate = true;
        });
    }

    /* Siparise gore renk: kimlik = {part_id: {order_id, ...}}; palet indeksi
     * order_id'lerin SIRALI listesinden (deterministik). */
    function siparisRengi(kimlik, palet) {
        const orderlar = [...new Set(Object.values(kimlik).map(k => k.order_id))].sort();
        const renkler = new Map(orderlar.map((o, i) =>
            [o, new THREE.Color(palet[i % palet.length])]));
        _renkUygula(pid => {
            const k = pid && kimlik[pid];
            return (k && renkler.get(k.order_id)) || RENK_NOTR;
        });
        return orderlar.map((o, i) => ({ order_id: o, renk: '#' +
            new THREE.Color(palet[i % palet.length]).getHexString() }));
    }

    /* Tip moduna donus: instanceColor birak, baked vertex-renklerini ac. */
    function tipRengi() {
        _renkUygula(() => new THREE.Color(0xffffff));  // instanceColor notr
        handle.gruplar.forEach(g => {
            g.material.vertexColors = true;
            g.material.needsUpdate = true;
        });
    }

    /* Rehberli sokum gorunumu: hedef parca vurgulu, digerleri soluk. */
    function vurgula(partId) {
        _renkUygula(pid => (pid === partId ? RENK_VURGU : RENK_NOTR));
    }

    function soluklastir() {
        _renkUygula(() => RENK_NOTR);
    }

    function temizle() { tipRengi(); }

    function resize(refit) {
        if (!handle.hazir) return;
        const sz = sizeFor();
        handle.renderer.setSize(sz.w, sz.h);
        handle.camera.aspect = sz.w / sz.h;
        handle.camera.updateProjectionMatrix();
        if (refit) {
            handle.controls.target.set(0, 0, 0);
            handle.camera.position.set(handle.size, handle.size * 0.8, handle.size * 1.2);
            handle.camera.lookAt(0, 0, 0);
            handle.controls.update();
        }
    }

    return handle;
}
