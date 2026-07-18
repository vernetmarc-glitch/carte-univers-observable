"""
Validation headless de la MATRICE zoom × temps (§11.6/§11.8/§13) et des
frames cuites par scripts/generate_spacetime_frames.py.

Réplique EXACTEMENT le pipeline d'affichage du prototype
app/public/spacetime-matrix-test.html (mêmes formules, mêmes données), puis
vérifie par le calcul, sur toute la grille zoom × temps :

  A. A(s,a) : A(s,1)=1 EXACTEMENT et continûment pour toute échelle
     (contrainte dure §11.4.b, avec le correctif de continuité du 13
     juillet pour les échelles à plancher actif, l3→l5).
  B. Non-régression à a=1 (§11.7) : la dernière frame de chaque layer GRF
     doit être identique à la texture de production (au 1/255 de
     quantification près). localgroup : seule différence volontaire =
     correctif §4.8 (moyenne cible 8.95/255, galaxies préservées).
  C. Séquences de frames : saturation, continuité moyenne/écart-type entre
     keyframes voisines, contenu haute fréquence (variance du laplacien)
     qui ne s'effondre pas tant que A > 0, état final plat quand A = 0.
  D. Composition affichée sur une grille dense (zooms × temps) :
     couverture complète du cadre (§11.4.f — aucun recadrage visible d'une
     frame structurée), continuité du ton le long des DEUX axes,
     embrasement atteignant le blanc à a_min, cohérence de luminosité
     moyenne entre layers voisins.

Sortie : rapport texte + montage PNG (grille de vignettes) pour la
confirmation visuelle FINALE de l'utilisateur (§13.1 : le retour visuel
est une confirmation, pas la méthode de détection).

Usage : cd scripts/dev && python3 validate_spacetime_matrix.py
"""
import json
import math
import sys
import numpy as np
from PIL import Image
from scipy.ndimage import laplace

from spacetime_pipeline import (
    MATRIX, LAYERS, BY_KEY, FRAMES, DATA_DIR, GAL_A_FORM, smoothstep,
    structure_amplitude_scale, A_layer, A_gal, white_channel,
    effective_halfwidth, expansion_strength, layer_weights, render_cell,
    composite_sprites, sprite_visibility, t_gyr_of_a, a_of_t_gyr, RG, SPR,
)

CANVAS_N = 160


FAILURES = []


def check(ok, label, detail=""):
    status = "OK " if ok else "ÉCHEC"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(f"{label} — {detail}")






# ═══ A. Contraintes sur A(s,a) ══════════════════════════════════════════
print("\n═══ A. Contraintes A(s,a) (§11.4.b) ═══")
a_dense = np.concatenate([10 ** np.linspace(math.log10(MATRIX["time_axis"]["a_min"]), 0, 4000), [1.0]])
STEP_DEX = (0 - math.log10(MATRIX["time_axis"]["a_min"])) / 3999
for entry in LAYERS:
    vals = np.array([A_layer(entry, a) for a in a_dense])
    at1 = A_layer(entry, 1.0)
    just_below = A_layer(entry, 1 - 1e-9)
    max_step = np.abs(np.diff(vals)).max()
    # Borne ANALYTIQUE de continuité : pente max d'un smoothstep = 1.5 sur
    # l'entrée t, t balayant [0,1] sur 2w dex -> ΔA_max = 1.5×pas/(2w).
    # Un vrai SAUT dépasserait largement cette borne ; une transition raide
    # mais lisse la respecte exactement.
    bound = 1.5 * STEP_DEX / (2 * entry["halfwidth_dex"]) * 1.25 + 1e-6
    check(at1 == 1.0, f"A({entry['key']}, a=1) = 1 exactement", f"valeur={at1}")
    check(abs(1 - just_below) < 1e-6, f"A({entry['key']}) continu en a=1⁻", f"A(1-1e-9)={just_below:.9f}")
    check(max_step <= bound, f"A({entry['key']}) continu (borne analytique de pente)",
          f"max ΔA={max_step:.5f} ≤ {bound:.5f}")
    check(bool(np.all(np.diff(vals) >= -1e-12)), f"A({entry['key']}) monotone croissant en a")

# Trace de l'ancien défaut (formule pré-correctif) pour mémoire :
def old_A(a_form, a):
    if a >= 1:
        return 1.0
    w = max(-math.log10(a_form), 0.05)
    x = math.log10(a) - math.log10(a_form)
    return float(smoothstep((x + w) / (2 * w)))
print(f"  (mémo : ancienne formule, l5 : A(1-1e-9)={old_A(1.0, 1-1e-9):.3f} → saut 1→0.5 corrigé)")

# ═══ B. Non-régression à a=1 (§11.7) ════════════════════════════════════
print("\n═══ B. Non-régression a=1 vs production ═══")
for entry in LAYERS:
    if not entry.get("frame_pattern"):
        continue   # milkyway : sprite + fond, aucune frame propre
    key = entry["key"]
    n_k = len(entry["keyframes_a"])
    baked = np.array(Image.open(f"{DATA_DIR}/st_{key}_k{n_k-1:02d}.png")).astype(np.float64)
    prod = np.array(Image.open(f"{DATA_DIR}/density_{key}.png").convert("L")).astype(np.float64)
    prod512 = prod  # v3.2 : frames au format production 1024, comparaison directe
    if key == "localgroup":
        # Seule différence volontaire : correctif §4.8. Vérifier la cible
        # calibrée et la préservation des galaxies (corrélation dans les
        # zones brillantes de la texture d'origine).
        mean = baked.mean()
        check(abs(mean - 8.95) < 0.8, "localgroup a=1 : moyenne cible §4.8 (8.95/255)", f"mesuré {mean:.2f}")
        bright = prod512 > 30
        corr = np.corrcoef(baked[bright], prod512[bright])[0, 1] if bright.sum() > 100 else 0
        check(corr > 0.95, "localgroup a=1 : galaxies préservées", f"corrélation zones brillantes={corr:.4f}")
        sat = (baked > 240).mean()
        check(sat < 0.01, "localgroup a=1 : saturation négligeable (§4.8)", f"{sat*100:.3f}% > 240")
    else:
        diff = np.abs(baked - prod512)
        check(diff.max() <= 1.0 + 1e-9, f"{key} a=1 identique à production (±1 quantif.)",
              f"max diff={diff.max():.3f}, moyenne diff={diff.mean():.4f}")

import spacetime_pipeline as _sp

# ═══ C. Séquences de frames ═════════════════════════════════════════════
print("\n═══ C. Séquences de frames (saturation, continuité, HF) ═══")
for entry in LAYERS:
    if not entry.get("frame_pattern"):
        continue   # milkyway : sprite + fond, aucune frame propre
    key = entry["key"]
    kfs = entry["keyframes_a"]
    imgs = FRAMES[key]
    means = np.array([im.mean() for im in imgs])
    stds = np.array([im.std() for im in imgs])
    laps = np.array([laplace(im).var() for im in imgs])
    sat_hi = np.array([(im > 240 / 255).mean() for im in imgs])

    dmean = np.abs(np.diff(means)).max()
    check(dmean < 0.10, f"{key} : continuité de moyenne entre keyframes", f"max Δmean={dmean*255:.1f}/255")
    # Saturation : les cœurs de galaxies de l1b/localgroup sont brillants par
    # conception — seuil large mais borné.
    # v3.2 : les nœuds de caustiques brillants SONT le look validé (la
    # référence Millennium en contient) — seuil élargi mais toujours borné.
    check(sat_hi.max() < 0.04, f"{key} : saturation bornée sur toute la séquence",
          f"max {sat_hi.max()*100:.2f}% > 240")
    # État initial (A=0) : uniforme PAR CONCEPTION (l'état dissous).
    a0 = kfs[0]
    A0 = max(A_layer(entry, a0), A_gal(a0) if entry.get("anchor_a1") or key == "localgroup" else 0)
    if A0 < 1e-6:
        check(stds[0] < 2 / 255, f"{key} : première frame (A=0) uniforme", f"std={stds[0]*255:.2f}/255")
    # HF : ne doit pas s'effondrer TANT QUE la structure existe (A>0.3),
    # puis DOIT décroître vers ~0 à l'état dissous (§11.2).
    for i, a in enumerate(kfs):
        if A_layer(entry, a) > 0.3 and laps[-1] > 0:
            frac = laps[i] / laps[-1]
            # v3.3 : sur localgroup les galaxies suivent la fenêtre de
            # CONDENSATION (galaxy_formation) — HF nulle attendue quand
            # A_sprite ~ 0, on ne contrôle que la fenêtre active.
            amp_ref = (_sp.A_sprite(a) if key == "localgroup" else A_layer(entry, a))
            if frac < 0.02 and amp_ref > 0.15:
                check(False, f"{key} : HF effondrée à a={a} malgré A={amp_ref:.2f}",
                      f"laplacien={frac*100:.1f}% de a=1")
                break
    else:
        check(True, f"{key} : HF cohérente (laplacien suit A, pas d'effondrement prématuré)",
              f"lapvar a=1 {laps[-1]:.2e} → première frame {laps[0]:.2e}")

# ═══ D. Composition affichée — grille zoom × temps ══════════════════════
print("\n═══ D. Grille composée zoom × temps (§11.4.f) ═══")










N_ZOOM, N_TIME = 15, 15
zooms = 10 ** np.linspace(math.log10(0.02), math.log10(14570), N_ZOOM)
times = np.concatenate([10 ** np.linspace(math.log10(MATRIX["time_axis"]["a_min"]), math.log10(0.999), N_TIME - 1), [1.0]])

mean_grid = np.zeros((N_ZOOM, N_TIME))
worst_clamp, worst_cell = 0.0, None
thumbs = {}
for zi, hw in enumerate(zooms):
    for ti, a in enumerate(times):
        tone, dbg = render_cell(hw, a)
        mean_grid[zi, ti] = tone.mean()
        if dbg["clamp"] > worst_clamp:
            worst_clamp, worst_cell = dbg["clamp"], (hw, a, dbg["hw_eff"])
        if zi % 2 == 0 and ti % 2 == 0:
            thumbs[(zi, ti)] = tone

check(worst_clamp < 0.05, "Couverture du cadre (§11.4.f) : aucun recadrage visible d'une frame structurée",
      f"pire défaut pondéré={worst_clamp*100:.2f}%" + (f" à hw={worst_cell[0]:.1f} a={worst_cell[1]:.4f} hw_eff={worst_cell[2]:.0f}" if worst_cell else ""))

# ── Continuité par BALAYAGES DENSES 1D (la grille du montage est trop
# grossière pour distinguer une transition raide-mais-lisse d'un saut).
# Preuve de lissité : on mesure max |Δmean| par pas à deux résolutions ;
# pour une fonction lisse, Δ décroît proportionnellement au pas — un vrai
# saut resterait constant.
def sweep_time(hw, n_pts):
    a_s = np.concatenate([10 ** np.linspace(math.log10(MATRIX["time_axis"]["a_min"]),
                                            math.log10(0.9999), n_pts - 1), [1.0]])
    return np.array([render_cell(hw, a)[0].mean() for a in a_s])

def sweep_zoom(a, n_pts):
    hws = 10 ** np.linspace(math.log10(0.02), math.log10(14570), n_pts)
    return np.array([render_cell(hw, a)[0].mean() for hw in hws])

print("  Balayages denses (continuité, §13.2.3)…")
for hw in [0.05, 5.0, 300.0, 14570.0]:
    m120 = sweep_time(hw, 120)
    m240 = sweep_time(hw, 240)
    d120, d240 = np.abs(np.diff(m120)).max(), np.abs(np.diff(m240)).max()
    # v3.2 : le fond dissous est passé de 129 à ~33/255 -> la pente de
    # l'embrasement (même plage de a, écart vers le blanc ×1.8) est
    # mécaniquement plus raide. La lissité RÉELLE est garantie par la preuve
    # de halving ci-dessous ; le seuil absolu est rescalé en proportion.
    check(d120 < 0.11, f"Continuité TEMPS à hw={hw} Mpc (120 pts)", f"max Δ/pas={d120:.4f}")
    check(d240 < d120 * 0.75, f"Lissité TEMPS à hw={hw} Mpc (Δ décroît avec le pas)",
          f"{d120:.4f} → {d240:.4f} en doublant la résolution")
for a in [1.0, 0.6, 0.15]:
    m120 = sweep_zoom(a, 120)
    m240 = sweep_zoom(a, 240)
    d120, d240 = np.abs(np.diff(m120)).max(), np.abs(np.diff(m240)).max()
    check(d120 < 0.06, f"Continuité ZOOM à a={a} (120 pts)", f"max Δ/pas={d120:.4f}")
    check(d240 < d120 * 0.75, f"Lissité ZOOM à a={a} (Δ décroît avec le pas)",
          f"{d120:.4f} → {d240:.4f} en doublant la résolution")

w_min = white_channel(MATRIX["time_axis"]["a_min"])
check(w_min > 0.995, "Embrasement : blanc à la recombinaison", f"white(a_min)={w_min:.4f}")
check(white_channel(0.15) < 0.02, "Embrasement : nul jusqu'à a≈0.1-0.15", f"white(0.15)={white_channel(0.15):.4f}")
tone_amin = mean_grid[:, 0]
check(bool(np.all(tone_amin > 0.98)), "Ton uniforme blanc à a_min sur TOUS les zooms",
      f"min={tone_amin.min():.4f}")

# ═══ E. Expansion par échelle (matrice v2 — problème 3 du 13/07) ═══
print("\n═══ E. Effet d'expansion par échelle ═══")
for hw in [0.05, 0.5, 1.2, 2.4]:
    effs = [effective_halfwidth(hw, a) for a in [1.0, 0.5, 0.2, 0.05, 0.001]]
    dev = max(abs(e - hw) for e in effs)
    check(dev < 1e-9, f"Aucune expansion à hw={hw} Mpc (volume lié)",
          f"écart max hw_eff−hw = {dev:.2e}")
for entry in LAYERS:
    if entry.get("expansion_strength") is None:
        continue
    s_meas = expansion_strength(entry["max_mpc"])
    check(abs(s_meas - entry["expansion_strength"]) < 1e-9,
          f"strength({entry['key']}) = valeur matrice",
          f"{s_meas:.3f} vs {entry['expansion_strength']}")
# Écart apparent MW–M31 CONSTANT dans le temps à l'échelle du Groupe Local :
def peak_of(tone, cx, cy, r=18):
    y0, y1 = max(0, cy - r), min(tone.shape[0], cy + r)
    x0, x1 = max(0, cx - r), min(tone.shape[1], cx + r)
    sub = tone[y0:y1, x0:x1]
    iy, ix = np.unravel_index(np.argmax(sub), sub.shape)
    return (x0 + ix, y0 + iy)


def centroid_of(residual, cx, cy, r=22):
    """Centre de masse du résidu sprite autour de (cx,cy) — plus stable que
    l'argmax face à l'évolution interne des frames N-corps."""
    y0, y1 = max(0, cy - r), min(residual.shape[0], cy + r)
    x0, x1 = max(0, cx - r), min(residual.shape[1], cx + r)
    sub = np.maximum(residual[y0:y1, x0:x1], 0)
    tot = sub.sum()
    if tot <= 1e-9:
        return (cx, cy)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    return (float((xs * sub).sum() / tot), float((ys * sub).sum() / tot))
CN = 300
m31 = next(g for g in RG if g["slug"] == "andromede")
import spacetime_pipeline as _spp
def mw_m31_dist(a):
    hw_eff = effective_halfwidth(1.2, a)
    bg = np.zeros((CN, CN))
    for k, w in layer_weights(hw_eff).items():
        t_, _, _ = _spp.layer_tone_map(BY_KEY[k], a, hw_eff, CN)
        bg += w * t_
    tone = composite_sprites(bg, a, hw_eff, CN)
    resid = tone - bg
    ppm = CN / (2 * hw_eff)
    ex = int(CN / 2 + math.cos(math.radians(m31["angle_deg"])) * m31["distance_mpc"] * ppm)
    ey = int(CN / 2 + math.sin(math.radians(m31["angle_deg"])) * m31["distance_mpc"] * ppm)
    c_mw = centroid_of(resid, CN // 2, CN // 2)
    c_m31 = centroid_of(resid, ex, ey)
    return math.dist(c_mw, c_m31)
# hw_eff(1.2, a) = 1.2 exactement (vérifié ci-dessus) et les ancrages de
# catalogue sont constants par construction -> la séparation géométrique est
# invariante. La tolérance 3px couvre le mouvement propre N-corps cuit dans
# les frames (accrétion, PAS de l'expansion).
# v3.3 : fenêtre de condensation — les sprites sont éteints à a=0.45 ;
# la constance de l'écart se mesure dans la fenêtre visible (a=0.85).
d_now, d_half = mw_m31_dist(1.0), mw_m31_dist(0.85)
check(abs(d_now - d_half) <= 3.0, "Écart apparent MW–M31 constant dans le temps (hw=1.2 Mpc, centroïdes)",
      f"{d_now:.1f}px (a=1) vs {d_half:.1f}px (a=0.85)")

# ═══ F. Sprites cuits (problèmes 1/4/5/6 du 13/07) ═══
print("\n═══ F. Sprites N-corps cuits ═══")
# a=1 : les 9 galaxies présentes à leurs positions de catalogue (hw=1.2).
tone1, dbg1 = render_cell(1.2, 1.0, canvas_n=CN)
fond1 = render_cell(1.2, 1.0, canvas_n=CN)  # même appel — le fond seul :
import spacetime_pipeline as _sp
_bg = np.zeros((CN, CN))
for k, w in dbg1["weights"].items():
    t_, _, _ = _sp.layer_tone_map(BY_KEY[k], 1.0, dbg1["hw_eff"], CN)
    _bg += w * t_
found = 0
ppm = CN / (2 * dbg1["hw_eff"])
for g in RG:
    gx = int(CN / 2 + math.cos(math.radians(g["angle_deg"])) * g["distance_mpc"] * ppm)
    gy = int(CN / 2 + math.sin(math.radians(g["angle_deg"])) * g["distance_mpc"] * ppm)
    if not (0 <= gx < CN and 0 <= gy < CN):
        continue
    resid_map = tone1 - _bg
    half_px_r = max(g["sprite_halfwidth_mpc"] * ppm,
                    SPR["min_render_core_px"] * g["sprite_halfwidth_units"])
    # Tolérance de position proportionnelle à la taille rendue : le pic de
    # résidu d'un grand sprite peut être un nœud de bras spiral hors centre
    # (morphologie N-corps légitime, cas de la Voie lactée : 8.1px/15px).
    tol = max(8.0, 0.6 * half_px_r)
    px, py = peak_of(resid_map, gx, gy, r=int(math.ceil(tol)))
    if resid_map[py, px] > 0.05 and math.dist((px, py), (gx, gy)) <= tol:
        found += 1
check(found == 9, "a=1 : les 9 galaxies réelles visibles à leurs positions (hw=1.2 Mpc)",
      f"{found}/9 pics de résidu détectés (≥0.05, tolérance ∝ taille rendue)")
# Extinction et séquencement : résidu sprite -> 0 AVANT la dissolution du fond.
def sprite_residual(a):
    hw_eff = effective_halfwidth(1.2, a)
    bg = np.zeros((CN, CN))
    for k, w in layer_weights(hw_eff).items():
        t_, _, _ = _sp.layer_tone_map(BY_KEY[k], a, hw_eff, CN)
        bg += w * t_
    with_spr = composite_sprites(bg, a, hw_eff, CN)
    return float(np.abs(with_spr - bg).max())
r_seq = {a: sprite_residual(a) for a in [1.0, 0.5, 0.3, 0.15, 0.08, 0.04, 0.02]}
check(r_seq[1.0] > 0.3, "Sprites bien visibles à a=1", f"résidu max={r_seq[1.0]:.3f}")
check(all(r_seq[a] <= r_seq[1.0] for a in r_seq), "Résidu sprite décroissant en remontant le temps",
      f"{ {k: round(v,4) for k, v in r_seq.items()} }")
check(r_seq[0.04] < 1e-4 and r_seq[0.02] < 1e-4, "Extinction complète des sprites à a≤0.04",
      f"résidu(0.04)={r_seq[0.04]:.2e}")
# Séquencement (décision du 13/07) : les sprites se dissolvent dans le fond
# AVANT que le fond ne se dissolve — vérifié EMPIRIQUEMENT : contraste
# sprite relatif (résidu(a)/résidu(1)) < contraste fond relatif MESURÉ
# (std_fond(a)/std_fond(1)), sur toute la fenêtre de dissolution.
def fond_std(a):
    he = effective_halfwidth(1.2, a)
    f = np.zeros((CN, CN))
    for k, w in layer_weights(he).items():
        t_, _, _ = _sp.layer_tone_map(BY_KEY[k], a, he, CN)
        f += w * t_
    return float(f.std())
std1 = fond_std(1.0)
seq_ok, seq_detail = True, []
for a in [0.5, 0.3, 0.15, 0.1]:
    s_rel = sprite_residual(a) / r_seq[1.0]
    f_rel = fond_std(a) / std1
    seq_detail.append(f"a={a}: sprite {s_rel:.3f} vs fond {f_rel:.3f}")
    # Le séquencement porte sur l'ORDRE DE DISPARITION : strict dès que la
    # dissolution est engagée (a<=0.35) ; à a=0.5 les deux sont quasi pleins
    # (>90%), tolérance de mesure 5%.
    tol = 1.05 if a >= 0.45 else 1.0
    if s_rel >= f_rel * tol:
        seq_ok = False
check(seq_ok, "Séquencement : les sprites se dissolvent dans le fond AVANT lui (mesuré)",
      " · ".join(seq_detail))
# Non-régression morphologies : corrélation f00 vs texture production (info).
for g in RG[:3]:
    f00 = np.array(Image.open(f"{DATA_DIR}/dissolution_sprites/{g['slug']}_f00.png").convert("L"))
    prod = np.array(Image.open(f"{DATA_DIR}/density_realgal_{g['slug']}.png").convert("L").resize((512, 512)))
    c = np.corrcoef(f00.ravel(), prod.ravel())[0, 1]
    print(f"  (info : corrélation sprite f00 vs density_realgal [{g['slug']}] = {c:.3f})")

# ═══ G. Axe de temps en Gyr (problème 2 du 13/07) ═══
print("\n═══ G. Axe de temps cosmique (Gyr, linéaire) ═══")
disp = MATRIX["time_axis"]["display"]
check(disp["mode"] == "cosmic_time_gyr_linear", "Mode d'affichage temporel linéaire en Gyr")
t_grid = np.linspace(disp["t_min_gyr"], disp["t_max_gyr"], 800)
a_grid = np.array([a_of_t_gyr(t) for t in t_grid])
check(bool(np.all(np.diff(a_grid) > 0)), "Mapping t→a strictement monotone (800 pts)")
rt = abs(t_gyr_of_a(a_of_t_gyr(5.0)) - 5.0)
check(rt < 1e-6, "Aller-retour t→a→t exact", f"|Δ|={rt:.2e} Gyr à t=5")
check(abs(a_of_t_gyr(disp["t_max_gyr"]) - 1.0) < 1e-3, "t_max correspond à a=1",
      f"a(t_max)={a_of_t_gyr(disp['t_max_gyr']):.5f}")
# L'embrasement doit être confiné au tout début de la course du curseur.
t_white = None
for t in np.linspace(disp["t_min_gyr"], 0.5, 3000):
    if white_channel(a_of_t_gyr(t)) < 0.99:
        t_white = t
        break
frac = (t_white - disp["t_min_gyr"]) / (disp["t_max_gyr"] - disp["t_min_gyr"])
check(frac < 0.01, "Embrasement (blanc>99%) confiné à <1% de la course du curseur",
      f"fin du blanc à t={t_white:.4f} Gyr = {frac*100:.2f}% de la course")
check(white_channel(a_of_t_gyr(1.0)) < 0.01, "Plus d'embrasement à t=1 Gyr",
      f"white={white_channel(a_of_t_gyr(1.0)):.4f}")

# ═══ H. Nomenclature des cellules (demande du 14/07) ═══
print("\n═══ H. Nomenclature des cellules ═══")
from spacetime_pipeline import cell_params, NOMEN
zr, tc = NOMEN["zoom_rows"], NOMEN["time_columns"]
check(len(zr) == sum(1 for l in LAYERS) and set(v["layer"] for v in zr.values()) == set(l["key"] for l in LAYERS),
      "Nomenclature : les lignes couvrent exactement tous les layers",
      f"{len(zr)} lignes / {len(LAYERS)} layers")
codes = sorted(zr.keys())
check(codes == [chr(ord('A') + i) for i in range(len(zr))],
      "Nomenclature : lettres consécutives depuis A", ",".join(codes))
hws = [zr[c]["halfwidth_mpc"] for c in codes]
check(all(hws[i] < hws[i + 1] for i in range(len(hws) - 1)),
      "Nomenclature : A = vue la plus rapprochée, ordre de zoom strictement croissant")
disp = MATRIX["time_axis"]["display"]
t_vals = [tc[str(k)]["t_gyr"] for k in range(11)]
check(abs(t_vals[0] - disp["t_min_gyr"]) < 1e-3 and abs(t_vals[-1] - disp["t_max_gyr"]) < 1e-3
      and all(abs((t_vals[k + 1] - t_vals[k]) - (t_vals[1] - t_vals[0])) < 2e-4 for k in range(10)),  # tolérance = arrondi 4 décimales du JSON
      "Nomenclature : colonnes 0..10 linéaires en Gyr, bornes = curseur",
      f"pas={t_vals[1]-t_vals[0]:.4f} Gyr")
for k in range(11):
    a_expected = a_of_t_gyr(tc[str(k)]["t_gyr"])
    assert abs(min(a_expected, 1.0) - tc[str(k)]["a"]) < 1e-4
check(True, "Nomenclature : a de chaque colonne cohérent avec la table cosmologique")
hw_d7, a_d7 = cell_params("D7")
check(abs(hw_d7 - 8.49) < 1e-9 and abs(a_d7 - tc["7"]["a"]) < 1e-9,
      "Nomenclature : résolution D7 = (l1b 8.49 Mpc, a(t7))", f"({hw_d7}, {a_d7})")
check(cell_params("A10")[0] == 0.04 and cell_params("B10")[0] == 0.1,
      "Nomenclature v3 : A = milkyway_hires (0.04 Mpc), B = milkyway (0.1 Mpc)")

# ── Montage de vignettes pour confirmation visuelle finale (§13.1).
ASTRO = np.array([[0, 0, 0], [0x17, 0x0a, 0x05], [0x4a, 0x1f, 0x0a],
                  [0xa8, 0x48, 0x0f], [0xe8, 0xa1, 0x3a], [0xff, 0xf3, 0xd6]], dtype=np.float64)


def colorize(tone):
    n = len(ASTRO) - 1
    idx = np.clip((tone * n).astype(int), 0, n - 1)
    frac = tone * n - idx
    return np.clip(ASTRO[idx] + (ASTRO[idx + 1] - ASTRO[idx]) * frac[..., None], 0, 255).astype(np.uint8)


# Grille CANONIQUE de la nomenclature : 12 lignes A..L (A en haut) ×
# 11 colonnes 0..10, chaque vignette rendue à la cellule exacte du code.
MCN = 140
LBL = 26
rows_m = [chr(ord('A') + i) for i in range(len(zr))]
cols_m = [str(k) for k in range(11)]
H = LBL + len(rows_m) * (MCN + 2)
W = LBL + len(cols_m) * (MCN + 2)
mont = np.zeros((H, W, 3), dtype=np.uint8)
for r, rc in enumerate(rows_m):
    for c, cc in enumerate(cols_m):
        hw_m, a_m = cell_params(rc + cc)
        tone_m, _ = render_cell(hw_m, a_m, canvas_n=MCN)
        y = LBL + r * (MCN + 2)
        x = LBL + c * (MCN + 2)
        mont[y:y + MCN, x:x + MCN] = colorize(tone_m)
img = Image.fromarray(mont)
from PIL import ImageDraw
draw = ImageDraw.Draw(img)
for r, rc in enumerate(rows_m):
    draw.text((8, LBL + r * (MCN + 2) + MCN // 2 - 6), rc, fill=(255, 220, 160))
for c, cc in enumerate(cols_m):
    draw.text((LBL + c * (MCN + 2) + MCN // 2 - 4, 8), cc, fill=(255, 220, 160))
img.save("spacetime_matrix_montage.png")
print(f"\nMontage écrit : scripts/dev/spacetime_matrix_montage.png "
      f"(grille nomenclature {len(rows_m)} lignes A..L × {len(cols_m)} colonnes 0..10, "
      f"A = Voie lactée en haut, temps -> droite)")

print("\n══════════════════════════════════════")
if FAILURES:
    print(f"{len(FAILURES)} ÉCHEC(S) :")
    for fmsg in FAILURES:
        print(f"  - {fmsg}")
    sys.exit(1)
print("TOUTES LES VÉRIFICATIONS PASSENT — le retour visuel peut être demandé (§13.4).")
