"""Prévisualisation v3 — itération 4 : générateur par ADVECTION DE ZEL'DOVICH.

La squelettisation par crêtes (itér. 2-3) produit de la mousse cellulaire,
pas la toile de la référence. Ici : le champ FFT (mêmes graines) sert de
potentiel, une grille de masse est advectée le long de ses gradients
(Psi_hat = i k delta_hat / k²), le dépôt CIC forme les caustiques — vrais
filaments, nœuds aux convergences, vides vidés. L'amplitude de déplacement
est le paramètre d'effondrement (=> dissolution temporelle exacte ensuite).

10 variantes réellement distinctes sur G10 (l3, 150 Mpc), même graine.
Sortie : preview_zeldovich_variantes.png
"""
import math
import sys
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "..")
from generate_layers import (
    N, LAYER_SPECS, margin_for, box_mpc, generate_raw_field,
    normalize_variance, crop_and_upsample,
)

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


# ── champ de base l3 (cascade, mêmes graines que la production)
print("1) Champ de base l3…")
W_COARSE, W_DETAIL = 0.74, 0.67
specs_by_key = {s["key"]: s for s in LAYER_SPECS}
raw = {}
for spec in LAYER_SPECS:
    key, margin, parent_key = spec["key"], margin_for(spec["key"]), spec["parent"]
    world = box_mpc(spec["max_mpc"], margin)
    if parent_key is None:
        base = normalize_variance(generate_raw_field(N, world, spec["seed"]))
    else:
        pp = specs_by_key[parent_key]
        coarse = crop_and_upsample(raw[parent_key], pp["max_mpc"], spec["max_mpc"],
                                   N, margin_for(parent_key), margin)
        k_tr = np.pi * N / box_mpc(pp["max_mpc"], margin_for(parent_key))
        detail = generate_raw_field(N, world, spec["seed"], highpass_k=k_tr)
        base = normalize_variance(coarse) * W_COARSE + normalize_variance(detail) * W_DETAIL
    raw[key] = base
    if key == "l3":
        break
DELTA = raw["l3"]
WORLD = box_mpc(specs_by_key["l3"]["max_mpc"], margin_for("l3"))
CUT_MPC = 150.0

# ── précalculs FFT
KY = np.fft.fftfreq(N)[:, None]
KX = np.fft.rfftfreq(N)[None, :]
K2 = KY ** 2 + KX ** 2
K = np.sqrt(K2)
K_CUT = WORLD / (CUT_MPC * N)          # lambda = 150 Mpc, en cycles/px


def displacement(delta, lam_min_px):
    """Psi = i k delta_hat / k², bande-limité lambda in [lam_min_px, 150 Mpc]."""
    D = np.fft.rfft2(delta)
    mask = (K >= K_CUT) & (K <= 1.0 / max(lam_min_px, 2.0)) & (K2 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        base = np.where(mask, D / K2, 0)
    psi_x = np.fft.irfft2(1j * KX * base / (2 * np.pi), s=delta.shape)
    psi_y = np.fft.irfft2(1j * KY * base / (2 * np.pi), s=delta.shape)
    rms = math.sqrt(psi_x.var() + psi_y.var()) + 1e-12
    return psi_x / rms, psi_y / rms


def bilinear(f, y, x):
    y0 = np.floor(y).astype(int) % N
    x0 = np.floor(x).astype(int) % N
    y1, x1 = (y0 + 1) % N, (x0 + 1) % N
    fy, fx = y - np.floor(y), x - np.floor(x)
    return (f[y0, x0] * (1 - fy) * (1 - fx) + f[y1, x0] * fy * (1 - fx)
            + f[y0, x1] * (1 - fy) * fx + f[y1, x1] * fy * fx)


def deposit_cic(y, x, n):
    rho = np.zeros((n, n))
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            np.add.at(rho, ((y0 + dy) % n, (x0 + dx) % n), wy * wx)
    return rho / rho.mean()


def blur_fft(f, sigma_px):
    if sigma_px <= 0:
        return f
    G = np.exp(-2 * (math.pi * sigma_px) ** 2 * K2)
    return np.fft.irfft2(np.fft.rfft2(f) * G, s=f.shape)


# grille de masse 1024² (4 particules / pixel de sortie)
NG = 1024
qy, qx = np.mgrid[0:NG, 0:NG] * (N / NG)
qy = qy.ravel()
qx = qx.ravel()

# scintillement fin (galaxies le long des brins) : champ HF propre
SPARK = generate_raw_field(N, WORLD, specs_by_key["l3"]["seed"] + 7000,
                           highpass_k=np.pi * N / (WORLD / 40))
SPARK = normalize_variance(SPARK)


def render(P):
    """P: S (déplacement rms px), lam_min (lissage brins px), second_pass,
    glow_sigma, glow_amp, spark_amp, alpha_shape, void_gamma."""
    px, py = displacement(DELTA, P["lam_min"])
    S = P["S"]
    y = qy + S * bilinear(py, qy, qx)
    x = qx + S * bilinear(px, qy, qx)
    if P.get("second_pass", 0) > 0:
        y = y + P["second_pass"] * S * bilinear(py, y, x)
        x = x + P["second_pass"] * S * bilinear(px, y, x)
    rho = deposit_cic(y, x, N)
    rho = blur_fft(rho, P.get("soft_px", 0.7))            # anti-crénelage doux
    # scintillement : petits amas brillants là où la densité est forte
    if P["spark_amp"] > 0:
        dots = np.clip(SPARK - 2.1, 0, None) * np.clip(rho, 0, 4)
        rho = rho + P["spark_amp"] * dots
    # exposition : t = 1 - exp(-alpha rho^shape), alpha calibré -> mean 38/255
    shape = P["alpha_shape"]
    rs = rho ** shape
    alphas = np.linspace(0.02, 2.5, 90)
    means = [np.mean((1 - np.exp(-a * rs)) ** P["void_gamma"]) for a in alphas]
    a = float(alphas[int(np.argmin(np.abs(np.array(means) - 38 / 255)))])
    t = (1 - np.exp(-a * rs)) ** P["void_gamma"]
    if P["glow_amp"] > 0:                                  # brume autour des brins
        t = np.clip(t + P["glow_amp"] * blur_fft(t, P["glow_sigma"]), 0, 1)
        # ré-expose après la brume
        t = t * (38 / 255) / max(t.mean(), 1e-6)
        t = np.clip(t, 0, 1)
    return t


VARIANTS = [
    ("Z1 jeune",        dict(S=6,  lam_min=6,  spark_amp=0.0, glow_sigma=0,  glow_amp=0.0)),
    ("Z2 toile",        dict(S=11, lam_min=6,  spark_amp=0.0, glow_sigma=0,  glow_amp=0.0)),
    ("Z3 toile+brume",  dict(S=11, lam_min=6,  spark_amp=0.0, glow_sigma=9,  glow_amp=0.9)),
    ("Z4 mure",         dict(S=16, lam_min=6,  spark_amp=0.0, glow_sigma=0,  glow_amp=0.0)),
    ("Z5 mure+brume",   dict(S=16, lam_min=7,  spark_amp=0.0, glow_sigma=10, glow_amp=1.1)),
    ("Z6 brins lisses", dict(S=14, lam_min=14, spark_amp=0.0, glow_sigma=8,  glow_amp=0.8)),
    ("Z7 galaxies",     dict(S=13, lam_min=7,  spark_amp=0.5, glow_sigma=8,  glow_amp=0.7)),
    ("Z8 effondre 2x",  dict(S=12, lam_min=7,  spark_amp=0.3, glow_sigma=8,  glow_amp=0.7,
                             second_pass=0.6)),
    ("Z9 dentelle",     dict(S=18, lam_min=5,  spark_amp=0.4, glow_sigma=6,  glow_amp=0.5)),
    ("Z10 reference",   dict(S=14, lam_min=9,  spark_amp=0.55, glow_sigma=11, glow_amp=1.0,
                             second_pass=0.5)),
]
BASEP = dict(second_pass=0.0, soft_px=0.7, alpha_shape=1.6, void_gamma=1.35)

print("2) Rendu des 10 variantes…")
tiles, tones, report = [], [], []
for name, over in VARIANTS:
    P = dict(BASEP)
    P.update(over)
    t = render(P)
    tones.append(t)
    sat = float((t > 245 / 255).mean())
    report.append((name, float(t.mean()), sat))
    tiles.append(labeled(colorize(t), f"{name} | S={P['S']} mean={t.mean()*255:.0f}"))
    print(f"   {name}")
rows = [np.concatenate(tiles[i:i + 5], axis=1) for i in (0, 5)]
grid = np.concatenate([rows[0], np.zeros((6, rows[0].shape[1], 3), np.uint8), rows[1]], axis=0)
Image.fromarray(grid).save("preview_zeldovich_variantes.png")

print("\n── Auto-contrôles ──")
ok = True
for name, mean, sat in report:
    v = 0.10 <= mean <= 0.20 and sat < 0.03
    print(f"  {name:16s} mean={mean*255:.0f} sat={sat*100:.2f}% {'OK' if v else 'HORS'}")
    ok &= v
# dissimilarité réelle entre variantes (hors paire jeune/mûre attendue proche)
import itertools
corrs = []
for (i, a), (j, b) in itertools.combinations(enumerate(tones), 2):
    corrs.append(np.corrcoef(a.ravel(), b.ravel())[0, 1])
corrs = np.array(corrs)
print(f"  corrélations inter-variantes : min={corrs.min():.2f} méd={np.median(corrs):.2f} max={corrs.max():.2f}")
ok &= (np.median(corrs) < 0.85)
print("\n" + ("AUTO-CONTRÔLES OK" if ok else "ÉCHEC — ne pas présenter"))
sys.exit(0 if ok else 1)
