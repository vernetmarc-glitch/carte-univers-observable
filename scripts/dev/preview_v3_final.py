"""Prévisualisation de CONTRÔLE pré-recuisson v3.2 (plan validé le 16/07).

Lit TOUS les paramètres depuis spacetime_matrix.json (bloc zeldovich) —
aucun paramètre local : ce script vérifie que ce qui est gravé reproduit
bien ce que Marc a validé (anti-dérive), avant la recuisson complète.

Sorties :
  preview_final_bande.png         — D10..M10 avec ancrages injectés dans δ
  preview_final_C_ambiante.png    — C10 sans / avec toile ambiante (0.35)
  preview_final_H_dissolution.png — H sur 6 pas de temps, loi S(a)=11·A^q
"""
import json
import math
import sys
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "..")
from generate_layers import (
    N, LAYER_SPECS, margin_for, box_mpc, generate_raw_field,
    normalize_variance, crop_and_upsample, apply_local_group_anchor,
)
from generate_local_group_catalog import build_catalog
from spacetime_pipeline import MATRIX, BY_KEY, A_layer

Z = MATRIX["zeldovich"]
WA = MATRIX["web_ambient"]
ROW_ORDER = ["l1b", "l2", "l2b", "l3", "l3b", "l4", "l4a", "l4b", "l5a", "l5"]
CODES = "DEFGHIJKLM"

ASTRO = np.array([[0, 0, 0], [0x17, 0x0a, 0x05], [0x4a, 0x1f, 0x0a],
                  [0xa8, 0x48, 0x0f], [0xe8, 0xa1, 0x3a], [0xff, 0xf3, 0xd6]],
                 dtype=np.float64)


def colorize(t):
    n = len(ASTRO) - 1
    idx = np.clip((t * n).astype(int), 0, n - 1)
    fr = t * n - idx
    return np.clip(ASTRO[idx] + (ASTRO[idx + 1] - ASTRO[idx]) * fr[..., None],
                   0, 255).astype(np.uint8)


def labeled(rgb, text):
    img = Image.fromarray(rgb)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width, 16], fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 220, 160))
    return np.array(img)


def hstack(imgs, pad=3):
    h = max(i.shape[0] for i in imgs)
    w = sum(i.shape[1] for i in imgs) + pad * (len(imgs) - 1)
    out = np.zeros((h, w, 3), dtype=np.uint8)
    x = 0
    for i in imgs:
        out[:i.shape[0], x:x + i.shape[1]] = i
        x += i.shape[1] + pad
    return out


# ═══ Cascade δ (héritage inchangé) + injection des ancrages dans δ ═══
print("1) Cascade δ + ancrages…")
catalog = build_catalog()
W_COARSE, W_DETAIL = 0.74, 0.67
specs_by_key = {s["key"]: s for s in LAYER_SPECS}
DELTAS, WORLDS = {}, {}
for spec in LAYER_SPECS:
    key, margin, parent_key = spec["key"], margin_for(spec["key"]), spec["parent"]
    world = box_mpc(spec["max_mpc"], margin)
    if parent_key is None:
        base = normalize_variance(generate_raw_field(N, world, spec["seed"]))
    else:
        pp = specs_by_key[parent_key]
        coarse = crop_and_upsample(DELTAS[parent_key + "_raw"], pp["max_mpc"],
                                   spec["max_mpc"], N, margin_for(parent_key), margin)
        k_tr = np.pi * N / box_mpc(pp["max_mpc"], margin_for(parent_key))
        detail = generate_raw_field(N, world, spec["seed"], highpass_k=k_tr)
        base = normalize_variance(coarse) * W_COARSE + normalize_variance(detail) * W_DETAIL
    DELTAS[key + "_raw"] = base            # héritage sur δ NON ancré
    anchor = BY_KEY[key].get("anchor_a1")
    if anchor:
        # v3.2 : bosses injectées dans δ AVANT advection (gs=1.0 depuis la matrice)
        base = apply_local_group_anchor(base, spec["max_mpc"], N, catalog, **anchor)
    DELTAS[key] = base
    WORLDS[key] = world
    print(f"   {key}")

# ═══ Advection de Zel'dovich (paramètres du bloc matrice) ═══
KY = np.fft.fftfreq(N)[:, None]
KX = np.fft.rfftfreq(N)[None, :]
K2 = KY ** 2 + KX ** 2
K = np.sqrt(K2)
NG = Z["mass_grid"]
qy, qx = np.mgrid[0:NG, 0:NG] * (N / NG)
qy, qx = qy.ravel(), qx.ravel()


def displacement(delta, world):
    D = np.fft.rfft2(delta)
    k_cut = world / (Z["filament_max_scale_mpc"] * N)
    mask = (K >= k_cut) & (K <= 1.0 / max(Z["lam_min_px"], 2.0)) & (K2 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        base = np.where(mask, D / K2, 0)
    px = np.fft.irfft2(1j * KX * base / (2 * np.pi), s=delta.shape)
    py = np.fft.irfft2(1j * KY * base / (2 * np.pi), s=delta.shape)
    rms = math.sqrt(px.var() + py.var()) + 1e-12
    return px / rms, py / rms


def bilinear(f, y, x):
    y0 = np.floor(y).astype(int) % N
    x0 = np.floor(x).astype(int) % N
    y1, x1 = (y0 + 1) % N, (x0 + 1) % N
    fy, fx = y - np.floor(y), x - np.floor(x)
    return (f[y0, x0] * (1 - fy) * (1 - fx) + f[y1, x0] * fy * (1 - fx)
            + f[y0, x1] * (1 - fy) * fx + f[y1, x1] * fy * fx)


def blur_fft(f, s):
    if s <= 0:
        return f
    G = np.exp(-2 * (math.pi * s) ** 2 * K2)
    return np.fft.irfft2(np.fft.rfft2(f) * G, s=f.shape)


PSI = {k: displacement(DELTAS[k], WORLDS[k]) for k in ROW_ORDER}


def density(key, S):
    if S <= 1e-3:
        return np.ones((N, N))
    px, py = PSI[key]
    y = qy + S * bilinear(py, qy, qx)
    x = qx + S * bilinear(px, qy, qx)
    rho = np.zeros((N, N))
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            np.add.at(rho, ((y0 + dy) % N, (x0 + dx) % N), wy * wx)
    rho /= rho.mean()
    # le flou FFT peut créer de petits négatifs -> ρ^shape = NaN : clip
    return np.clip(blur_fft(rho, Z["soft_px"]), 0, None)


print("2) Densités a=1 (S=%.0f px)…" % Z["s_px_a1"])
RHO1 = {k: density(k, Z["s_px_a1"] * (BY_KEY[k]["zeldovich_s_px"] / Z["s_px_a1"]))
        for k in ROW_ORDER}

# ═══ Exposition : α GLOBAL poolé D..M -> 38/255 (bloc zeldovich.exposure) ═══
shape = Z["exposure"]["shape"]
vg = Z["exposure"]["void_gamma"]
alphas = np.linspace(0.02, 2.5, 100)
means = [np.mean([np.mean((1 - np.exp(-a * RHO1[k] ** shape)) ** vg) for k in ROW_ORDER])
         for a in alphas]
ALPHA = float(alphas[int(np.argmin(np.abs(np.array(means) - 38 / 255)))])
DISS_TONE = float((1 - math.exp(-ALPHA)) ** vg)
print(f"3) α global = {ALPHA:.3f} | ton dissous = {DISS_TONE*255:.1f}/255")


def tone_of(rho):
    return (1 - np.exp(-ALPHA * rho ** shape)) ** vg


# ═══ Panneau 1 : bande D10..M10 ═══
tiles, means_row = [], {}
for code, key in zip(CODES, ROW_ORDER):
    t = tone_of(RHO1[key])
    means_row[code] = float(t.mean())
    tiles.append(labeled(colorize(t)[::2, ::2], f"{code}10 ({key}) m={t.mean()*255:.0f}"))
Image.fromarray(hstack(tiles)).save("preview_final_bande.png")

# ═══ Panneau 2 : C10 sans / avec toile ambiante ═══
lg = np.array(Image.open("../../app/public/data/st_localgroup_k11.png").convert("L")) / 255
t_d = tone_of(RHO1["l1b"])
world_d = WORLDS["l1b"]
frac = 2 * 2.4 / world_d                     # fenêtre C dans la texture D
c0 = int(N / 2 - N / 2 * frac)
c1 = int(N / 2 + N / 2 * frac)
web_c = np.array(Image.fromarray((t_d[c0:c1, c0:c1] * 255).astype(np.uint8))
                 .resize((512, 512), Image.BILINEAR)) / 255
amp_c = WA["amplitudes"]["localgroup"]
c_with = 1 - (1 - lg) * (1 - web_c * amp_c)   # screen
p2 = [labeled(colorize(lg), f"C10 actuel m={lg.mean()*255:.0f}"),
      labeled(colorize(c_with), f"C10 + toile ambiante {amp_c} m={c_with.mean()*255:.0f}"),
      labeled(colorize(t_d)[::1, ::1], f"D10 (référence continuité) m={t_d.mean()*255:.0f}")]
Image.fromarray(hstack(p2)).save("preview_final_C_ambiante.png")

# ═══ Panneau 3 : dissolution H, loi S(a) = s_px × A^q ═══
q = Z["temporal"]["q"]
A_VALS = [1.0, 0.96, 0.92, 0.88, 0.84, 0.80]
h_tiles, h_stats = [], []
for a in A_VALS:
    A = A_layer(BY_KEY["l3b"], a)
    S = BY_KEY["l3b"]["zeldovich_s_px"] * (A ** q)
    t = tone_of(density("l3b", S))
    h_stats.append((a, A, S, float(t.mean()), float(t.std())))
    h_tiles.append(labeled(colorize(t)[::2, ::2],
                           f"a={a} S={S:.1f}px m={t.mean()*255:.0f}"))
Image.fromarray(hstack(h_tiles)).save("preview_final_H_dissolution.png")

# ═══ Auto-contrôles ═══
print("\n── Auto-contrôles ──")
ok = True
for code, mean in means_row.items():
    v = 0.10 <= mean <= 0.20
    print(f"  {code}10 mean={mean*255:.0f}/255 {'OK' if v else 'HORS'}")
    ok &= v
sat = max(float((tone_of(RHO1[k]) > 245 / 255).mean()) for k in ("l1b", "l3"))
print(f"  saturation max (D,G) : {sat*100:.2f}% {'OK' if sat < 0.03 else 'ÉCHEC'}")
ok &= sat < 0.03
# anti-dérive : G10 doit reproduire la variante Z2 validée (même layer l3, mêmes params)
# grille iter4 : tuiles de N px (=1024) SANS padding, bandeau 16 px en haut
g_old = Image.open("preview_zeldovich_variantes.png").crop((N, 32, 2 * N, N)).convert("L").resize((256, 256))
g_new = Image.fromarray((tone_of(RHO1["l3"])[32:] * 255).astype(np.uint8)).convert("L").resize((256, 256))
corr = float(np.corrcoef(np.array(g_old, dtype=float).ravel(),
                         np.array(g_new, dtype=float).ravel())[0, 1])
print(f"  anti-dérive G10 vs Z2 validée : corr={corr:.3f} {'OK' if corr > 0.9 else 'ÉCHEC'}")
ok &= corr > 0.9
# garantie des maxima : les vraies galaxies restent des pics de ρ (ligne D)
found = 0
rho_d = RHO1["l1b"]
world_d_half = world_d / 2
n_in = 0
for g in catalog:
    if not g.get("isReal"):
        continue
    r = math.radians(g["angleDeg"])
    gx = N / 2 + math.cos(r) * g["distanceMpc"] / world_d * N
    gy = N / 2 + math.sin(r) * g["distanceMpc"] / world_d * N
    if not (10 < gx < N - 10 and 10 < gy < N - 10):
        continue
    n_in += 1
    y0, y1 = int(gy) - 10, int(gy) + 10
    x0, x1 = int(gx) - 10, int(gx) + 10
    sub = rho_d[y0:y1, x0:x1]
    ring = rho_d[max(0, y0 - 15):y1 + 15, max(0, x0 - 15):x1 + 15]
    if sub.max() >= np.percentile(ring, 98):
        found += 1
print(f"  galaxies réelles = pics de ρ (ligne D) : {found}/{n_in} {'OK' if found >= n_in - 1 else 'ÉCHEC'}")
ok &= found >= n_in - 1
# dissolution : lisse + convergence vers le ton dissous
gaps = [abs(h_stats[i][3] - h_stats[i + 1][3]) for i in range(len(h_stats) - 1)]
conv = abs(h_stats[-1][3] - DISS_TONE) if h_stats[-1][2] < 1 else None
stds = [s[4] for s in h_stats]
mono_std = all(stds[i] >= stds[i + 1] - 0.005 for i in range(len(stds) - 1))
print(f"  dissolution H : saut max {max(gaps)*255:.1f}/255 {'OK' if max(gaps) < 0.06 else 'ÉCHEC'} ; "
      f"contraste décroissant {'OK' if mono_std else 'ÉCHEC'} ; "
      f"std final {stds[-1]*255:.1f}")
ok &= max(gaps) < 0.06 and mono_std
print(f"  toile ambiante C : Δmean = {(c_with.mean()-lg.mean())*255:+.1f}/255 (info)")
print("\n" + ("AUTO-CONTRÔLES OK — présentable" if ok else "ÉCHEC — ne pas présenter"))
sys.exit(0 if ok else 1)
