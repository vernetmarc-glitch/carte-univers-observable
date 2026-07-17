"""Prévisualisation v3 — itération 3 (retours Marc du 16/07).

1. UN SEUL visuel Voie lactée : le sprite milkyway_hires f00 pleine
   résolution (2048², disque ~1024 px), densifié (passe cœur + passe halo).
   -> preview_mw_sprite.png
2. 10 variantes paramétriques du générateur de champ filamenteux sur la
   cellule G10 (l3, 150 Mpc), pour choix du caractère "toile d'araignée".
   -> preview_filaments_variantes.png
"""
import json
import math
import sys
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "..")
from generate_layers import (
    N, LAYER_SPECS, margin_for, box_mpc, generate_raw_field,
    normalize_variance, field_to_log_density, crop_and_upsample,
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


# ═══════════════════════════════════════════════════════════════════════
# 1) Sprite Voie lactée pleine résolution (un seul visuel)
# ═══════════════════════════════════════════════════════════════════════
print("1) Sprite Voie lactée…")
mwsim = json.load(open("../../app/public/data/milkyway_dissolution_keyframes.json"))
NH, HWU = 2048, 2.0
RAD_LY = mwsim["mwRadiusLy"]
pos0 = np.array(mwsim["frames"][0]["positions"])
meta = mwsim["particleMeta"]
bvals = np.array([m["b"] for m in meta])
szvals = np.array([m["sz"] for m in meta])
ppu = NH / (2 * HWU * RAD_LY)
xs = NH / 2 + pos0[:, 0] * ppu
ys = NH / 2 + pos0[:, 1] * ppu
amps = 0.18 + bvals * 0.55
sig_core = np.clip(szvals * (NH / 1024), 0.8, 6.0)


def splat(field, sig_arr, amp_arr):
    for x, y, amp, sg in zip(xs, ys, amp_arr, sig_arr):
        r = int(math.ceil(sg * 3.0))
        if x < -r or x >= NH + r or y < -r or y >= NH + r:
            continue
        x0, x1 = max(0, int(x - r)), min(NH, int(x + r) + 1)
        y0, y1 = max(0, int(y - r)), min(NH, int(y + r) + 1)
        gy, gx = np.mgrid[y0:y1, x0:x1]
        field[y0:y1, x0:x1] += amp * np.exp(-((gx - x) ** 2 + (gy - y) ** 2) / (2 * sg * sg))


fld = np.zeros((NH, NH))
splat(fld, sig_core, amps * 0.7)                 # passe cœur : étoiles nettes
splat(fld, sig_core * 3.5, amps * 0.22)          # passe halo : bras pleins
nz = fld[fld > 1e-4]
kcal = -math.log(1 - 0.95) / np.percentile(nz, 99.7)
tone_mw = 1 - np.exp(-fld * kcal)
edge = int(NH * 0.06)
ramp = 0.5 - 0.5 * np.cos(np.linspace(0, math.pi, edge))
ax = np.ones(NH)
ax[:edge] = ramp
ax[-edge:] = ramp[::-1]
tone_mw *= ax[None, :] * ax[:, None]
Image.fromarray(colorize(tone_mw)).save("preview_mw_sprite.png")
sat_mw = float((tone_mw > 0.99).mean())
print(f"   sprite 2048² écrit, saturation>0.99 : {sat_mw*100:.2f}%")

# ═══════════════════════════════════════════════════════════════════════
# 2) 10 variantes du champ filamenteux sur G10 (l3)
# ═══════════════════════════════════════════════════════════════════════
print("2) Champ de base l3 (cascade)…")
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
BASE = raw["l3"]
WORLD = box_mpc(specs_by_key["l3"]["max_mpc"], margin_for("l3"))
CUT = 150.0


def filamentize_var(field, world, P):
    """Squelettisation paramétrée — P: weights, p, gain, env_mix, env_slope,
    glow_sigma_px, glow_amp, spine, ridge_mix."""
    F = np.fft.rfft2(field)
    ky = np.fft.fftfreq(field.shape[0])[:, None]
    kx = np.fft.rfftfreq(field.shape[1])[None, :]
    k = np.hypot(ky, kx)
    k_cut = world / (CUT * field.shape[0])
    low = np.fft.irfft2(F * (k < k_cut), s=field.shape)
    high = field - low
    edges = [1 / 128, 1 / 32, 1 / 8, 0.5]
    web = np.zeros_like(field)
    tot = 0.0
    sig_ref = field.std() + 1e-12
    for (k_lo, k_hi), w in zip(zip(edges[:-1], edges[1:]), P["weights"]):
        b = np.fft.irfft2(F * ((k >= max(k_lo, k_cut)) & (k < k_hi)), s=field.shape)
        s = b.std()
        if s < 1e-4 * sig_ref:
            continue
        n01 = np.clip(0.5 + b / (3.2 * s), 0, 1)
        web += w * (1 - np.abs(2 * n01 - 1) ** P["p"])
        tot += w
    if tot < 1e-9:
        return field
    web = np.clip(web / tot, 0, 1) ** P.get("spine", 1.0)   # accent des épines
    if P.get("glow_amp", 0) > 0:                             # halo autour des brins
        gs = P["glow_sigma_px"]
        gk = np.exp(-2 * (math.pi * gs) ** 2 * k ** 2)
        halo = np.fft.irfft2(np.fft.rfft2(web) * gk, s=field.shape)
        web = web + P["glow_amp"] * halo
    web = (web - web.mean()) / (web.std() + 1e-12)
    k_mod = max(k_cut, 3.0 / field.shape[0])
    low_mod = np.fft.irfft2(F * (k < k_mod), s=field.shape)
    ls = low_mod.std() + 1e-12
    z = np.clip(P["env_slope"] * low_mod / ls, -30, 30)
    env = 1 / (1 + np.exp(-z))
    mod = (1 - P["env_mix"]) + P["env_mix"] * env
    sig_h = high.std() + 1e-12
    mix = P["ridge_mix"]
    out = low + (1 - mix) * high + mix * web * mod * sig_h * P["gain"]
    return normalize_variance(out)


def export_var(field, target=38 / 255, void_gamma=1.5):
    ld = field_to_log_density(field)
    v0, v1 = np.percentile(ld, [1, 99.7])
    t = np.clip((ld - v0) / (v1 - v0), 0, 1) ** void_gamma
    gammas = np.linspace(0.5, 4.0, 80)
    means = [np.mean(t ** g) for g in gammas]
    g = float(gammas[int(np.argmin(np.abs(np.array(means) - target)))])
    return t ** g, g


BASEP = dict(weights=[0.45, 0.33, 0.22], p=1.5, gain=2.6, env_mix=0.75,
             env_slope=2.2, glow_sigma_px=0, glow_amp=0.0, spine=1.0, ridge_mix=0.85)
VARIANTS = [
    ("V1 base v3.1", {}),
    ("V2 brins longs", dict(weights=[0.70, 0.22, 0.08])),
    ("V3 longs+fins", dict(weights=[0.70, 0.22, 0.08], p=0.9)),
    ("V4 longs+halo", dict(weights=[0.70, 0.22, 0.08], glow_sigma_px=6, glow_amp=0.55)),
    ("V5 fins+gain fort", dict(p=0.8, gain=3.4)),
    ("V6 epais doux", dict(p=2.4, glow_sigma_px=4, glow_amp=0.3)),
    ("V7 vides profonds", dict(env_slope=4.0, env_mix=0.9)),
    ("V8 toile dense", dict(env_mix=0.4, weights=[0.6, 0.28, 0.12])),
    ("V9 epines+halo", dict(spine=1.7, glow_sigma_px=7, glow_amp=0.7, gain=3.0)),
    ("V10 araignee max", dict(weights=[0.72, 0.20, 0.08], p=0.9, env_slope=3.0,
                              gain=3.2, glow_sigma_px=8, glow_amp=0.75, spine=1.4)),
]
tiles = []
report = []
for name, over in VARIANTS:
    P = dict(BASEP)
    P.update(over)
    t, g = export_var(filamentize_var(BASE, WORLD, P))
    sat = float((t > 245 / 255).mean())
    report.append((name, float(t.mean()), sat, g))
    tiles.append(labeled(colorize(t), f"{name} | mean={t.mean()*255:.0f} g={g:.1f}"))
rows = [np.concatenate(tiles[i:i + 5] + [np.zeros_like(tiles[0])] * (5 - len(tiles[i:i + 5])),
        axis=1) for i in range(0, 10, 5)]
grid = np.concatenate([rows[0], np.zeros((6, rows[0].shape[1], 3), np.uint8), rows[1]], axis=0)
Image.fromarray(grid).save("preview_filaments_variantes.png")

print("\n── Auto-contrôles ──")
ok = sat_mw < 0.05
print(f"  MW saturation : {sat_mw*100:.2f}% {'OK' if sat_mw < 0.05 else 'ÉCHEC'}")
for name, mean, sat, g in report:
    v_ok = 0.09 <= mean <= 0.20 and sat < 0.02
    print(f"  {name:18s} mean={mean*255:.0f} sat={sat*100:.2f}% {'OK' if v_ok else 'HORS'}")
    ok &= v_ok
print("\n" + ("AUTO-CONTRÔLES OK" if ok else "ÉCHEC — ne pas présenter"))
sys.exit(0 if ok else 1)
