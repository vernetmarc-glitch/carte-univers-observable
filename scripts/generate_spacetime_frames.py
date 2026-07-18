"""
Cuit les frames temporelles de TOUS les layers de densité (l1b→l5 +
localgroup) à partir de la matrice canonique zoom × temps
(app/public/data/spacetime_matrix.json, cf. §11.6 et
docs/matrice-parametres-zoom-temps.md).

Mécanismes appliqués (aucun autre — §11.3) :
- Champ GRF de chaque layer : reproduit EXACTEMENT le pipeline de
  production (generate_layers.py, mêmes seeds, même héritage, même
  normalisation partagée) puis, pour a<1, le champ gaussien PRÉ-transformation
  est multiplié par A(s_layer, a) (§11.2/§11.4.b). La topologie (phases) ne
  change jamais — grille comobile figée (§2).
- Ancrage Groupe Local (l1b/l2/l2b) : les amplitudes additionnées et la
  profondeur de suppression sont multipliées par A(s_galaxies=0.03, a) —
  l'ancrage se dissout avec les GALAXIES, pas avec le layer hôte (§11.4.b).
- localgroup : champ des ~90 galaxies procédurales × A_gal(a) + fond FFT
  résiduel §4.8 (amplitude 0.35 à a=1) × A_gal(a) + plancher uniforme
  (1−A_gal(a)) × ton_dissous_GRF pour que la luminosité moyenne converge
  vers le MÊME état uniforme que les layers de densité (§11.1 point 3).
  À a=1 : production + correctif §4.8 — la seule différence volontaire
  avec la production actuelle (§11.7).
- Normalisation FIGÉE : vmin/vmax partagés calculés UNE FOIS sur les champs
  a=1 (comme la production), réutilisés pour toutes les frames (§13.3).
- L'embrasement (§11.4.c) n'est PAS cuit : c'est un canal ajouté à
  l'affichage par mélange "screen", identique pour tous les layers.

Sortie : app/public/data/st_{layer}_k{ii}.png (512×512, niveaux de gris —
palette au runtime, comme toutes les textures du projet), + champ "computed"
réécrit dans spacetime_matrix.json (vmin/vmax figés, tons mesurés).

Usage : cd scripts && python3 generate_spacetime_frames.py
Validation obligatoire ensuite : scripts/dev/validate_spacetime_matrix.py (§13).
"""
import json
import math
import numpy as np
from PIL import Image

from generate_layers import (
    N, LAYER_SPECS, margin_for, box_mpc, generate_raw_field,
    normalize_variance, crop_and_upsample, field_to_log_density,
    apply_local_group_anchor,
)
from generate_local_group_catalog import build_catalog
import generate_local_group_texture as lgt

MATRIX_PATH = "../app/public/data/spacetime_matrix.json"
OUT_DIR = "../app/public/data"

with open(MATRIX_PATH) as f:
    MATRIX = json.load(f)

LAYERS_BY_KEY = {l["key"]: l for l in MATRIX["layers"]}


# ── A(s,a) — port EXACT de spacetime-shared.js (avec le correctif de
# continuité du 13 juillet : la fenêtre se termine toujours à a=1).
def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def structure_amplitude(layer_entry, a):
    if a >= 1:
        return 1.0
    w = layer_entry["halfwidth_dex"]
    center = layer_entry["center_dex"]
    x = math.log10(max(a, 1e-6)) - center
    return smoothstep((x + w) / (2 * w))


GAL_ENTRY = LAYERS_BY_KEY["localgroup"]  # même a_form/fenêtre que l'échelle galaxies


def a_gal(a):
    return structure_amplitude(GAL_ENTRY, a)


# ── 1. Reproduire les champs de base de production (pré-ancrage) et les
# champs finaux a=1 (post-ancrage), exactement comme generate_layers.main().
print("1) Régénération des champs de production (a=1)…")
catalog = build_catalog()
W_COARSE, W_DETAIL = 0.74, 0.67
specs_by_key = {s["key"]: s for s in LAYER_SPECS}

base_fields = {}   # pré-ancrage (hérite des parents POST-ancrage, comme en prod)
prod_fields = {}   # post-ancrage = champs de production a=1

for spec in LAYER_SPECS:
    key, margin, parent_key = spec["key"], margin_for(spec["key"]), spec["parent"]
    if parent_key is None:
        base = normalize_variance(generate_raw_field(N, box_mpc(spec["max_mpc"], margin), spec["seed"]))
    else:
        p = specs_by_key[parent_key]
        coarse = crop_and_upsample(prod_fields[parent_key], p["max_mpc"], spec["max_mpc"],
                                   N, margin_for(parent_key), margin)
        k_tr = np.pi * N / box_mpc(p["max_mpc"], margin_for(parent_key))
        detail = generate_raw_field(N, box_mpc(spec["max_mpc"], margin), spec["seed"], highpass_k=k_tr)
        base = normalize_variance(coarse) * W_COARSE + normalize_variance(detail) * W_DETAIL
    base_fields[key] = base

    anchor = LAYERS_BY_KEY[key].get("anchor_a1")
    prod_fields[key] = (apply_local_group_anchor(base, spec["max_mpc"], N, catalog, **anchor)
                        if anchor else base)
    print(f"   {key} ok")

# ── 2. Exposition v3.2 : α GLOBAL calibré par generate_layers.py (matrice
# computed.zeldovich) — EXACTEMENT le même que les textures de production.
import zeldovich_engine as ze
GROWTH = ze.load_growth()
DISSOLVED_TONE = ze.dissolved_tone()
Q_TEMPORAL = MATRIX["zeldovich"]["temporal"]["q"]
GF = MATRIX["galaxy_formation"]


def a_sprite(a):
    """Fenêtre de formation des galaxies (v3.3, condensation APRÈS les nuages)."""
    x = math.log10(max(a, 1e-6)) - GF["center_dex"]
    t = (x + GF["halfwidth_dex"]) / (2 * GF["halfwidth_dex"])
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


print(f"2) v3.3 : G={GROWTH:.4f}, ton maintenu {DISSOLVED_TONE*255:.0f}/255, "
      f"q={Q_TEMPORAL}, a_form_sprites={GF['a_form_sprites']}")

def export_frame(norm01, path):
    """Export au format PRODUCTION : 1024², 8 bits — identique aux textures
    density_* de l'application (décision du 17/07 : aucune recuisson après
    le prototypage, les frames sont directement utilisables en production)."""
    Image.fromarray((np.clip(norm01, 0, 1) * 255).astype(np.uint8), mode="L").save(path)
    return norm01


def anchor_modulated(base_scaled, spec, entry, ag):
    """Applique l'ancrage Groupe Local avec ses amplitudes × A_gal(a).
    À ag=1 : strictement identique à l'appel de production."""
    p = dict(entry["anchor_a1"])
    p["strength"] = p["strength"] * ag
    if not p.get("diffuse", False):
        gs = p.get("global_suppression", 1.0)
        # L'assombrissement du champ ambiant se relâche avec la dissolution
        # des galaxies (gs -> 1 quand A_gal -> 0).
        p["global_suppression"] = 1.0 - (1.0 - gs) * ag
    return apply_local_group_anchor(base_scaled, spec["max_mpc"], N, catalog, **p)


# ── 3. Cuisson des frames GRF — moteur zeldovich, loi S(s,a) = s_px × A^q.
# Ancrages temporels : δ(a) = δ_brut + (δ_ancré − δ_brut) × A_gal(a) —
# la CONTRIBUTION des bosses suit A_gal (à A_gal=1 : champ de production
# exact ; à A_gal=0 : champ brut), puis Ψ est recalculé (le flot se
# reconnecte aux galaxies au fil de leur formation).
print("3) Cuisson des frames…")
computed_layers = {}
for entry in MATRIX["layers"]:
    key = entry["key"]
    if entry["kind"] != "grf":
        continue
    spec = specs_by_key[key]
    world = box_mpc(spec["max_mpc"], margin_for(key))
    has_anchor = bool(entry.get("anchor_a1"))
    if not has_anchor:
        psi = ze.displacement(base_fields[key], world)
    anchor_contrib = (prod_fields[key] - base_fields[key]) if has_anchor else None
    stats = []
    for i, a in enumerate(entry["keyframes_a"]):
        aL = structure_amplitude(entry, a)
        S = GROWTH * (aL ** Q_TEMPORAL)            # v3.3 : G global, Ψ comobile
        if has_anchor:
            # bosses de galaxies : fenêtre de CONDENSATION (a_form_sprites)
            delta_a = base_fields[key] + anchor_contrib * a_sprite(a)
            psi_a = ze.displacement(delta_a, world)
        else:
            psi_a = psi
        rho = ze.density_from_psi(psi_a, S, N)
        tone = ze.tone(rho, ze.solve_alpha(rho))   # α par frame : ton maintenu
        small = export_frame(tone, f"{OUT_DIR}/st_{key}_k{i:02d}.png")
        stats.append({"a": a, "A_layer": round(aL, 5), "A_gal": round(a_gal(a), 5),
                      "S_px": round(S, 3),
                      "mean": round(float(small.mean() * 255), 3),
                      "std": round(float(small.std() * 255), 3)})
    computed_layers[key] = stats
    print(f"   {key}: {len(stats)} frames (moyenne {stats[0]['mean']:.1f} -> {stats[-1]['mean']:.1f})")

# ── 4. localgroup — champ procédural + fond §4.8 + plancher de convergence.
print("   localgroup…")
lg_entry = LAYERS_BY_KEY["localgroup"]
lg_field = lgt.build_field(catalog, lgt.MAX_MPC, lgt.N, margin_factor=lgt.MARGIN_FACTOR)
rb = lg_entry["residual_bg"]
lg_bg = normalize_variance(generate_raw_field(
    lgt.N, 2 * lgt.MAX_MPC * lgt.MARGIN_FACTOR, seed=rb["seed"]))
VMAX_LG = rb["vmax_reference"]

stats = []
for i, a in enumerate(lg_entry["keyframes_a"]):
    ag = a_sprite(a)   # v3.3 : fenêtre de condensation
    floor = (1.0 - ag) * DISSOLVED_TONE * VMAX_LG
    # Formule §4.8 exacte : champ existant + amplitude × champ FFT normalisé
    # (les valeurs négatives du champ FFT sont écrêtées par le clip d'export,
    # comme dans la calibration d'origine), le tout modulé par A_gal(a).
    field = (lg_field + lg_bg * rb["amplitude_a1"]) * ag + floor
    norm = np.clip(field / VMAX_LG, 0, 1)
    small = export_frame(norm, f"{OUT_DIR}/st_localgroup_k{i:02d}.png")
    stats.append({"a": a, "A_layer": round(ag, 5), "A_gal": round(ag, 5),
                  "mean": round(float(small.mean() * 255), 3),
                  "std": round(float(small.std() * 255), 3)})
computed_layers["localgroup"] = stats
print(f"   localgroup: {len(stats)} frames (moyenne {stats[0]['mean']:.1f} -> {stats[-1]['mean']:.1f})")

# ── 5. Réécrire "computed" dans la matrice (traçabilité, cf. §13.3 :
# normalisation figée UNE fois, réutilisée partout).
MATRIX["computed"] = {
    "zeldovich": MATRIX.get("computed", {}).get("zeldovich"),   # α de generate_layers.py
    "dissolved_tone_255": round(DISSOLVED_TONE * 255, 2),
    "per_layer_frames": computed_layers,
}
with open(MATRIX_PATH, "w") as f:
    json.dump(MATRIX, f, indent=1, ensure_ascii=False)
print("5) Matrice mise à jour (champ 'computed').")
print("Terminé — lancer scripts/dev/validate_spacetime_matrix.py avant tout retour visuel (§13).")
