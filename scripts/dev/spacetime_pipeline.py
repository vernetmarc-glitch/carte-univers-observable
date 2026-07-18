"""
Pipeline headless PARTAGÉ de composition zoom × temps — port Python 1:1 du
prototype app/public/spacetime-matrix-test.html (fonction computeTone) et
des formules de app/public/spacetime-shared.js.

SOURCE UNIQUE côté validation : validate_spacetime_matrix.py et tout futur
contrôle croisé importent ce module au lieu de recopier les formules
(cf. §11.4 "une seule définition, réutilisée partout" et §13).
Toute évolution du prototype/du JS partagé doit être répercutée ici.
"""
import json
import math
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

DATA_DIR = "../../app/public/data"

MATRIX = json.load(open(f"{DATA_DIR}/spacetime_matrix.json"))
LAYERS = MATRIX["layers"]
BY_KEY = {l["key"]: l for l in LAYERS}

FRAMES = {}
for _entry in LAYERS:
    FRAMES[_entry["key"]] = [
        np.array(Image.open(f"{DATA_DIR}/st_{_entry['key']}_k{i:02d}.png")).astype(np.float64) / 255
        for i in range(len(_entry["keyframes_a"]))]

with open(f"{DATA_DIR}/local_group_catalog.json") as f:
    CATALOG = json.load(f)

# Mapping temps cosmique (affichage linéaire en Gyr, matrice v2)
COSMO_ROWS = json.load(open(f"{DATA_DIR}/cosmology_table.json"))["rows"]


# ── Nomenclature des cellules (matrice.nomenclature) : "C7" -> (hw, a)
NOMEN = MATRIX.get("nomenclature", {})


def cell_params(code):
    """Résout un code de cellule (ex "C7") en (halfwidth_mpc, a)."""
    code = code.strip().upper()
    row, col = code[0], code[1:]
    zr = NOMEN["zoom_rows"][row]
    tc = NOMEN["time_columns"][col]
    return zr["halfwidth_mpc"], tc["a"]


def t_gyr_of_a(a):
    rows = COSMO_ROWS
    if a <= rows[0]["a"]:
        return rows[0]["t_Gyr"]
    for i in range(len(rows) - 1):
        if rows[i]["a"] <= a <= rows[i + 1]["a"]:
            f = (a - rows[i]["a"]) / (rows[i + 1]["a"] - rows[i]["a"])
            return rows[i]["t_Gyr"] + (rows[i + 1]["t_Gyr"] - rows[i]["t_Gyr"]) * f
    return rows[-1]["t_Gyr"]


def a_of_t_gyr(t):
    rows = COSMO_ROWS
    if t <= rows[0]["t_Gyr"]:
        return rows[0]["a"]
    for i in range(len(rows) - 1):
        if rows[i]["t_Gyr"] <= t <= rows[i + 1]["t_Gyr"]:
            f = (t - rows[i]["t_Gyr"]) / (rows[i + 1]["t_Gyr"] - rows[i]["t_Gyr"])
            return rows[i]["a"] + (rows[i + 1]["a"] - rows[i]["a"]) * f
    return rows[-1]["a"]


# ── A(s,a) — port exact de spacetime-shared.js (correctif continuité 13/07).
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def structure_amplitude_scale(a_form, a):
    if a >= 1:
        return 1.0
    w = max(-math.log10(a_form), 0.05)
    center = min(math.log10(a_form), -w)
    x = math.log10(max(a, 1e-6)) - center
    return float(smoothstep((x + w) / (2 * w)))


def A_layer(entry, a):
    return structure_amplitude_scale(entry["a_form"], a)


GAL_A_FORM = BY_KEY["localgroup"]["a_form"]


def A_gal(a):
    return structure_amplitude_scale(GAL_A_FORM, a)


EMB = MATRIX["embrasement"]


def white_channel(a):
    fade = 1 - structure_amplitude_scale(GAL_A_FORM, min(a * EMB["a_multiplier"], 1))
    return 1 - math.exp(-(fade ** EMB["exp"]) * EMB["offset_max"])


# Effet d'expansion PAR ÉCHELLE (matrice v2, 13/07) : interpolation
# smoothstep en log10(s) entre les nœuds validés — remplace la rampe
# globale lo=2/hi=15 qui contractait le champ des 96 galaxies liées.
EXP_NODES = MATRIX["expansion"]["nodes"]


def expansion_strength(scale_mpc):
    x = math.log10(max(scale_mpc, 1e-6))
    nodes = [(math.log10(s), v) for s, v in EXP_NODES]
    if x <= nodes[0][0]:
        return nodes[0][1]
    if x >= nodes[-1][0]:
        return nodes[-1][1]
    for i in range(len(nodes) - 1):
        if nodes[i][0] <= x <= nodes[i + 1][0]:
            span = nodes[i + 1][0] - nodes[i][0]
            t = float(smoothstep((x - nodes[i][0]) / span)) if span else 0.0
            return nodes[i][1] + (nodes[i + 1][1] - nodes[i][1]) * t
    return nodes[-1][1]


def effective_halfwidth(hw, a):
    return hw + (hw / max(a, 1e-6) - hw) * expansion_strength(hw)


# ── Poids de layers — port de app/src/layerWeights.ts (frontières lues dans
# la matrice), avec la simplification du prototype : poids "milkyway"
# reporté sur "localgroup" (la Voie lactée est rendue par son sprite).
ZA = MATRIX["zoom_axis"]
ORDER = ZA["layer_order"]
EDGES = [math.log10(e) for e in ZA["layer_edges_mpc"]]
FADES = ZA["fade_widths_dex"]


def layer_weights(hw):
    x = math.log10(max(hw, 1e-6))
    gates = [float(smoothstep((x - (e - f)) / (2 * f))) for e, f in zip(EDGES, FADES)]
    weights, remaining = {}, 1.0
    for i in range(len(ORDER) - 1):
        weights[ORDER[i]] = remaining * (1 - gates[i])
        remaining *= gates[i]
    weights[ORDER[-1]] = remaining
    weights["localgroup"] = weights.get("localgroup", 0) + weights.pop("milkyway", 0)
    return {k: v for k, v in weights.items() if v > 1e-3}


def _mip_for(frame, texel_per_px):
    """Moyenne de zone : niveau mip = plus grande puissance de 2 <= ratio,
    borné à 8 — identique au prototype JS (contrôle croisé)."""
    if texel_per_px < 2:
        return frame, frame.shape[0]
    f = 2
    while f * 2 <= min(texel_per_px, 8):
        f *= 2
    n = frame.shape[0]
    m = frame[:n - n % f, :n - n % f].reshape(n // f, f, n // f, f).mean(axis=(1, 3))
    return m, m.shape[0]


def layer_tone_map(entry, a, hw_eff, canvas_n):
    """Frame temporelle interpolée du layer, échantillonnée sur le cadre
    (fenêtre comobile ±hw_eff). Retourne (tone, fraction hors-texture par
    axe avant clamp, std de la frame)."""
    kfs = entry["keyframes_a"]
    imgs = FRAMES[entry["key"]]
    if a <= kfs[0]:
        frame = imgs[0]
    elif a >= kfs[-1]:
        frame = imgs[-1]
    else:
        i1 = int(np.searchsorted(kfs, a))
        i0 = i1 - 1
        frac = (math.log10(a) - math.log10(kfs[i0])) / (math.log10(kfs[i1]) - math.log10(kfs[i0]))
        frame = imgs[i0] * (1 - frac) + imgs[i1] * frac
    extent = entry["max_mpc"] * entry["margin_factor"]
    # v3.3 : moyenne de zone quand la fenêtre MINIFIE la texture (sans elle,
    # les petits filaments de K/L/M sont avalés par l'échantillonnage ponctuel)
    ratio = (hw_eff / extent) * frame.shape[0] / canvas_n
    frame, n_tex = _mip_for(frame, ratio)
    lin = (np.arange(canvas_n) + 0.5) / canvas_n * 2 - 1
    mpc = lin * hw_eff
    tex = (mpc / (2 * extent) + 0.5) * (n_tex - 1)
    out_frac = float(((tex < 0) | (tex > n_tex - 1)).mean())
    yy, xx = np.meshgrid(tex, tex, indexing="ij")
    tone = map_coordinates(frame, [yy, xx], order=1, mode="nearest")
    return tone, out_frac, float(frame.std())


# ── Sprites N-corps CUITS (matrice v2, 13/07) — les 126 frames
# dissolution_sprites/{slug}_f00..13.png remplacent les splats runtime.
SPR = MATRIX["sprites"]
RG = MATRIX["real_galaxies"]["entries"]
HIRES = MATRIX["real_galaxies"]["milkyway_hires"]
HIRES_FRAMES = [
    np.array(Image.open(f"{DATA_DIR}/dissolution_sprites_hires/milkyway_f{i:02d}.png")
             .convert("L")).astype(np.float64) / 255
    for i in range(HIRES["n_frames"])]
SPRITE_FRAMES = {}
for _g in RG:
    SPRITE_FRAMES[_g["slug"]] = [
        np.array(Image.open(
            f"{DATA_DIR}/dissolution_sprites/{_g['slug']}_f{i:02d}.png"
        ).convert("L")).astype(np.float64) / 255
        for i in range(SPR["n_frames"])]


WA = MATRIX["web_ambient"]
_AMB_NODES = [(0.04, WA["amplitudes"]["milkyway_hires"]),
              (0.1, WA["amplitudes"]["milkyway"]),
              (2.4, WA["amplitudes"]["localgroup"])]


def ambient_amplitude(hw_eff):
    x = math.log10(max(hw_eff, 1e-6))
    pts = [(math.log10(s), v) for s, v in _AMB_NODES]
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        if pts[i][0] <= x <= pts[i + 1][0]:
            t = float(smoothstep((x - pts[i][0]) / (pts[i + 1][0] - pts[i][0])))
            return pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
    return pts[-1][1]


GF = MATRIX["galaxy_formation"]


def A_sprite(a):
    """Fenêtre de formation des galaxies (v3.3 : condensation APRÈS les nuages)."""
    x = math.log10(max(a, 1e-6)) - GF["center_dex"]
    t = (x + GF["halfwidth_dex"]) / (2 * GF["halfwidth_dex"])
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def sprite_visibility(hw_eff):
    """Fondu en S de la zone sprites sur le demi-champ effectif."""
    lo, hi = SPR["visible_fade_band_mpc"]
    return 1.0 - float(smoothstep((math.log10(max(hw_eff, 1e-6)) - math.log10(lo))
                                  / (math.log10(hi) - math.log10(lo))))


def composite_sprites(bg, a, hw_eff, canvas_n):
    """Compose les sprites cuits sur le fond en mélange "screen" (§11.3).
    progress = 1−A_gal(a) -> paire de frames interpolée ;
    extinction = A_gal(a)^fade_exponent (les sprites se dissolvent dans le
    fond AVANT la dissolution du fond lui-même) ; visibilité fondue sur la
    bande visible_fade_band_mpc."""
    ag = A_sprite(a)          # v3.3 : les galaxies se condensent APRÈS les nuages
    vis = sprite_visibility(hw_eff)
    fade = (ag ** SPR["fade_exponent"]) * vis
    if fade <= 1e-4:
        return bg
    progress = 1 - ag
    fpos = progress * (SPR["n_frames"] - 1)
    i0 = min(int(fpos), SPR["n_frames"] - 2)
    mix = fpos - i0
    px_per_mpc = canvas_n / (2 * hw_eff)
    cx = cy = canvas_n / 2
    # Fondu de ZOOM 512 <-> hires pour la Voie lactée (bande matrice)
    lo_h, hi_h = HIRES["used_fade_band_mpc"]
    w_hires = 1.0 - float(smoothstep((math.log10(max(hw_eff, 1e-6)) - math.log10(lo_h))
                                     / (math.log10(hi_h) - math.log10(lo_h))))
    out = bg.copy()
    passes = []
    for g in RG:
        if g["slug"] == "milkyway" and w_hires > 1e-3:
            passes.append((g, SPRITE_FRAMES["milkyway"], g["sprite_halfwidth_mpc"],
                           g["sprite_halfwidth_units"], 1.0 - w_hires))
            passes.append((g, HIRES_FRAMES, HIRES["sprite_halfwidth_mpc"],
                           HIRES["sprite_halfwidth_units"], w_hires))
        else:
            passes.append((g, SPRITE_FRAMES[g["slug"]], g["sprite_halfwidth_mpc"],
                           g["sprite_halfwidth_units"], 1.0))
    for g, frames, hw_mpc, hw_units, w_pass in passes:
        if w_pass <= 1e-3:
            continue
        frame = frames[i0] * (1 - mix) + frames[i0 + 1] * mix
        n_spr = frame.shape[0]
        rad = math.radians(g["angle_deg"])
        gx = cx + math.cos(rad) * g["distance_mpc"] * px_per_mpc
        gy = cy + math.sin(rad) * g["distance_mpc"] * px_per_mpc
        # Plancher de lisibilité sur le CŒUR (cf. matrice sprites.min_render_comment)
        half_px = max(hw_mpc * px_per_mpc,
                      SPR["min_render_core_px"] * hw_units)
        x0 = max(0, int(math.floor(gx - half_px)))
        x1 = min(canvas_n, int(math.ceil(gx + half_px)) + 1)
        y0 = max(0, int(math.floor(gy - half_px)))
        y1 = min(canvas_n, int(math.ceil(gy + half_px)) + 1)
        if x1 <= x0 or y1 <= y0 or half_px <= 0:
            continue
        ys = (np.arange(y0, y1) + 0.5 - gy) / (2 * half_px) + 0.5
        xs = (np.arange(x0, x1) + 0.5 - gx) / (2 * half_px) + 0.5
        tv = np.clip(ys, 0, 1) * (n_spr - 1)
        tu = np.clip(xs, 0, 1) * (n_spr - 1)
        inside = ((ys >= 0) & (ys <= 1))[:, None] * ((xs >= 0) & (xs <= 1))[None, :]
        yy, xx = np.meshgrid(tv, tu, indexing="ij")
        tone = map_coordinates(frame, [yy, xx], order=1, mode="nearest") * inside
        sub = out[y0:y1, x0:x1]
        out[y0:y1, x0:x1] = 1 - (1 - sub) * (1 - tone * fade * w_pass)
    return out


def render_cell(hw, a, canvas_n=160):
    """Pipeline d'affichage complet — MÊMES formules que computeTone() du
    prototype spacetime-matrix-test.html."""
    hw_eff = effective_halfwidth(hw, a)
    weights = layer_weights(hw_eff)
    bg = np.zeros((canvas_n, canvas_n))
    clamp_defect = 0.0
    for key, w in weights.items():
        tone, out_frac, f_std = layer_tone_map(BY_KEY[key], a, hw_eff, canvas_n)
        bg += w * tone
        clamp_defect += w * out_frac * (f_std > 0.005)
    # Toile ambiante A/B/C (matrice web_ambient) : la texture de la ligne D
    # échantillonnée sur la fenêtre, × amplitude(hw) × part de zone C —
    # continuité C/D automatique (même toile), fondue quand D prend le relais.
    w_lg = weights.get("localgroup", 0.0)
    if w_lg > 1e-3:
        amb = ambient_amplitude(hw_eff) * w_lg
        if amb > 1e-3:
            web, _, _ = layer_tone_map(BY_KEY["l1b"], a, hw_eff, canvas_n)
            bg = 1 - (1 - bg) * (1 - web * amb)
    bg = composite_sprites(bg, a, hw_eff, canvas_n)
    white = white_channel(a)
    tone = 1 - (1 - bg) * (1 - white)       # embrasement en "screen", §11.4.c
    clamp_visible = clamp_defect * (1 - white)
    return tone, {"hw_eff": hw_eff, "white": white, "clamp": clamp_visible,
                  "weights": weights}
