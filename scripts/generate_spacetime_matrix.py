"""
Génère la MATRICE CANONIQUE de paramètres zoom × temps (§11.6 du document
d'architecture) : app/public/data/spacetime_matrix.json

Ce script ne produit AUCUN visuel — il fige, en un seul document versionnable,
tous les paramètres qui pilotent la génération des frames temporelles
(scripts/generate_spacetime_frames.py) et leur composition à l'affichage
(app/public/spacetime-matrix-test.html, et à terme la production).

RÈGLE D'AJUSTEMENT FUTUR : le JSON exporté est la SOURCE DE VÉRITÉ, éditable
à la main. Ce script ne sert qu'à le (re)construire depuis zéro si besoin —
relancer ce script ÉCRASE les ajustements manuels du JSON. Le flux normal
d'ajustement est : éditer le JSON -> relancer generate_spacetime_frames.py
-> relancer scripts/dev/validate_spacetime_matrix.py.

Provenance des valeurs : cf. docs/matrice-parametres-zoom-temps.md (chaque
champ y est documenté avec sa référence de section du doc d'architecture).
"""
import json
import math

OUT_PATH = "../app/public/data/spacetime_matrix.json"

# ── Mapping temps cosmique (table Planck déjà déployée)
_COSMO = json.load(open("../app/public/data/cosmology_table.json"))["rows"]
def _t_of_a(a_target):
    rows = _COSMO
    for i in range(len(rows) - 1):
        if rows[i]["a"] <= a_target <= rows[i + 1]["a"]:
            f = (a_target - rows[i]["a"]) / (rows[i + 1]["a"] - rows[i]["a"])
            return rows[i]["t_Gyr"] + (rows[i + 1]["t_Gyr"] - rows[i]["t_Gyr"]) * f
    return rows[0]["t_Gyr"] if a_target < rows[0]["a"] else rows[-1]["t_Gyr"]
T_MIN_GYR = round(_t_of_a(1.0 / 1101.0), 6)
T_MAX_GYR = round(_t_of_a(1.0), 4)

# ── Entrées galaxies réelles (catalogue + étendues monde des sprites cuits)
_CATALOG = json.load(open("../app/public/data/local_group_catalog.json"))
_KEYFRAMES = json.load(open("../app/public/data/dissolution_keyframes.json"))
_SLUG_BY_NAME = {
    'Andromède (M31)': 'andromede', 'Triangulum (M33)': 'triangulum',
    'Grand Nuage de Magellan': 'lmc', 'Petit Nuage de Magellan': 'smc',
    'Naine du Sagittaire': 'sagittaire', 'NGC 6822': 'ngc6822',
    'IC 10': 'ic10', 'Leo I': 'leo1',
}
def _sprite_halfwidth_units(slug):
    last = _KEYFRAMES[slug]["frames"][-1]["positions"]
    return max(max(abs(x), abs(y)) for x, y in last) * 1.15
REAL_GALAXY_ENTRIES = [{
    "slug": "milkyway", "name": "Voie lactée", "distance_mpc": 0.0,
    "angle_deg": 0.0, "radius_mpc": 0.01594329,
    "sprite_halfwidth_units": round(_sprite_halfwidth_units("milkyway"), 4),
    "sprite_halfwidth_mpc": round(_sprite_halfwidth_units("milkyway") * 0.01594329, 6),
}]
for _g in _CATALOG:
    if _g.get("isReal") and _g["name"] in _SLUG_BY_NAME:
        _slug = _SLUG_BY_NAME[_g["name"]]
        _hw = _sprite_halfwidth_units(_slug)
        REAL_GALAXY_ENTRIES.append({
            "slug": _slug, "name": _g["name"], "distance_mpc": _g["distanceMpc"],
            "angle_deg": _g["angleDeg"], "radius_mpc": _g["radiusMpc"],
            "sprite_halfwidth_units": round(_hw, 4),
            "sprite_halfwidth_mpc": round(_hw * _g["radiusMpc"], 6),
        })

# ── Filamentarité à l'échelle de chaque layer (v3, 14/07 — valeurs de départ
# à calibrer ; la coupure passe-bande filament_max_scale_mpc fait déjà
# l'essentiel du travail d'uniformisation aux lignes L/M)
RIDGE_MIX_AT_LAYER = {"l1b": 0.85, "l2": 0.85, "l2b": 0.85, "l3": 0.85,
                      "l3b": 0.8, "l4": 0.75, "l4a": 0.7, "l4b": 0.6,
                      "l5a": 0.5, "l5": 0.4}

# ── Effet d'expansion à l'échelle de chaque layer (nœuds validés 13/07)
EXPANSION_AT_LAYER = {"localgroup": 0.0, "l1b": 0.15, "l2": 0.65,
                      "l2b": 0.9, "l3": 1.0, "l3b": 1.0, "l4": 1.0,
                      "l4a": 1.0, "l4b": 1.0, "l5a": 1.0, "l5": 1.0}

# ── a_form(s) — points de contrôle, §11.4.a (identiques à spacetime-shared.js)
A_FORM_CONTROL_POINTS = [
    (math.log10(0.01), 0.20), (math.log10(2.4), 0.20), (math.log10(8.49), 0.55),
    (math.log10(30), 0.65), (math.log10(67), 0.70), (math.log10(150), 0.92),
    (math.log10(2100), 0.95), (math.log10(14570), 1.0),
]

def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)

def a_form_for_scale(scale_mpc):
    log_s = math.log10(max(scale_mpc, 1e-6))
    cps = A_FORM_CONTROL_POINTS
    if log_s <= cps[0][0]:
        return cps[0][1]
    if log_s >= cps[-1][0]:
        return cps[-1][1]
    for i in range(len(cps) - 1):
        if cps[i][0] <= log_s <= cps[i + 1][0]:
            span = cps[i + 1][0] - cps[i][0]
            t = smoothstep((log_s - cps[i][0]) / span) if span else 0.0
            return cps[i][1] + (cps[i + 1][1] - cps[i][1]) * t
    return cps[-1][1]

def transition_window(a_form):
    """Fenêtre de dissolution [a_debut, 1] en a, cohérente avec le correctif
    de continuité du 13 juillet dans spacetime-shared.js (§11.4.b) :
    largeur w = max(-log10(a_form), 0.05), centre = min(log10(a_form), -w),
    la fenêtre se termine TOUJOURS exactement à a=1."""
    w = max(-math.log10(a_form), 0.05)
    center = min(math.log10(a_form), -w)
    return 10 ** (center - w), w, center

def log_keyframes(a_lo, a_hi, k):
    """k valeurs de a, log-uniformes de a_lo à a_hi inclus (croissant)."""
    lo, hi = math.log10(a_lo), math.log10(a_hi)
    return [round(10 ** (lo + (hi - lo) * i / (k - 1)), 6) for i in range(k)]

# ── Échelle "galaxies" pour tout ce qui suit la dissolution des galaxies
# elles-mêmes (ancrages Groupe Local, sprites, embrasement) — §11.4.b/c.
GALAXY_SCALE_MPC = 0.03
A_FORM_GAL = a_form_for_scale(GALAXY_SCALE_MPC)          # 0.20
A_START_GAL, _, _ = transition_window(A_FORM_GAL)         # 0.04

K_TRANSITION = 9   # keyframes dans la fenêtre de dissolution du layer
K_ANCHOR_TAIL = 4  # keyframes supplémentaires (queue de dissolution de l'ancrage)

# ── Layers de densité procéduraux (mêmes clés/échelles/seeds/parents que
# scripts/generate_layers.py LAYER_SPECS — NE PAS diverger) + localgroup.
GRF_SPECS = [
    ("l5", 14570.0, 42, None, 2.4),
    ("l5a", 5531.46, 48, "l5", 1.5),
    ("l4b", 2100.0, 55, "l5", 1.5),
    ("l4a", 793.73, 61, "l4b", 1.5),
    ("l4", 300.0, 101, "l4b", 1.5),
    ("l3b", 212.13, 108, "l4", 1.5),
    ("l3", 150.0, 102, "l4", 1.5),
    ("l2b", 67.08, 112, "l3", 1.5),
    ("l2", 30.0, 103, "l3", 1.5),
    ("l1b", 8.49, 117, "l2", 1.5),
]

# Paramètres d'ancrage Groupe Local à a=1 — copie EXACTE de
# generate_layers.py main() (7 juillet, itérations 3-5). La modulation
# temporelle (multiplication par A_gal(a)) est décrite champ par champ dans
# docs/matrice-parametres-zoom-temps.md.
ANCHORS_A1 = {
    "l1b": {"strength": 1.0, "global_suppression": 0.35, "size_multiplier": 1.8,
            "real_only": False, "bump_amplitude_factor": 0.50, "extra_blur_px": 0.6,
            "diffuse": False},
    "l2": {"strength": 1.6, "real_only": False, "diffuse": True,
           "size_multiplier": 5.0, "bump_amplitude_factor": 2.6},
    "l2b": {"strength": 0.85, "real_only": False, "diffuse": True,
            "size_multiplier": 5.0, "bump_amplitude_factor": 1.7},
}

layers = []
for key, max_mpc, seed, parent, margin in GRF_SPECS:
    a_form = a_form_for_scale(max_mpc)
    a_start, w_dex, center_dex = transition_window(a_form)
    anchored = key in ANCHORS_A1
    keyframes = log_keyframes(a_start, 1.0, K_TRANSITION)
    if anchored and A_START_GAL < a_start:
        # Queue : l'ancrage (échelle galaxies) se dissout PLUS TARD en
        # remontant le temps que le champ du layer lui-même (§11.4.b).
        tail = log_keyframes(A_START_GAL, a_start, K_ANCHOR_TAIL + 1)[:-1]
        keyframes = tail + keyframes
    layers.append({
        "key": key,
        "kind": "grf",
        "max_mpc": max_mpc,
        "margin_factor": margin,
        "seed": seed,
        "parent": parent,
        "a_form": round(a_form, 4),
        "dissolution_window_a": [round(a_start, 6), 1.0],
        "halfwidth_dex": round(w_dex, 4),
        "center_dex": round(center_dex, 4),
        "compression": True,   # flux de Hubble — cf. bloc "expansion", §11.4.e
        "expansion_strength": EXPANSION_AT_LAYER[key],
        "anchor_a1": ANCHORS_A1.get(key),
        "anchor_scale_mpc": GALAXY_SCALE_MPC if anchored else None,
        "keyframes_a": keyframes,
        "frame_pattern": f"data/st_{key}_k{{:02d}}.png",
        "frame_resolution": 1024,   # format production (17/07)
    })

# localgroup — texture procédurale (98 galaxies) + fond FFT résiduel §4.8.
lg_keyframes = log_keyframes(A_START_GAL, 1.0, 12)
layers.append({
    "key": "localgroup",
    "kind": "procedural_galaxies",
    "max_mpc": 2.4,
    "margin_factor": 1.5,
    "seed": None,
    "parent": None,
    "a_form": A_FORM_GAL,
    "dissolution_window_a": [round(A_START_GAL, 6), 1.0],
    "halfwidth_dex": round(max(-math.log10(A_FORM_GAL), 0.05), 4),
    "center_dex": round(math.log10(A_FORM_GAL), 4),
    "compression": False,  # Groupe Local lié gravitationnellement, §11.4.e
    "expansion_strength": 0.0,
    "anchor_a1": None,
    "anchor_scale_mpc": GALAXY_SCALE_MPC,
    "residual_bg": {  # §4.8 — calibré le 10 juillet, intégré ici (§11.7)
        "amplitude_a1": 0.35,
        "seed": 31415,
        "vmax_reference": 4.074,
        "target_mean_a1": 8.95,   # /255, mesuré §4.8
    },
    # Ton uniforme de convergence : le même que l'état dissous des layers
    # GRF (field_to_log_density(0) normalisé par le vmin/vmax partagé de
    # production) — calculé et inscrit par generate_spacetime_frames.py
    # dans "computed". Cohérence de luminosité §11.1 point 3.
    "uniform_floor": "match_grf_dissolved_tone",
    "keyframes_a": lg_keyframes,
    "frame_pattern": "data/st_localgroup_k{:02d}.png",
    "frame_resolution": 1024,   # format production (17/07)
})

# ── Layer milkyway : la Voie lactée est rendue par son sprite N-corps
# (dissolution_sprites/milkyway_f*.png) posé sur le FOND localgroup
# (frames st_localgroup_* échantillonnées sur la fenêtre + plancher de
# convergence). Réintégré le 13 juillet (perdu dans la première version).
layers.append({
    "key": "milkyway",
    "kind": "sprite_plus_fond",
    "max_mpc": 0.1,                    # frontière layerWeights (0.1 Mpc)
    "margin_factor": None,
    "seed": None,
    "parent": None,
    "a_form": A_FORM_GAL,
    "dissolution_window_a": [round(A_START_GAL, 6), 1.0],
    "halfwidth_dex": round(max(-math.log10(A_FORM_GAL), 0.05), 4),
    "center_dex": round(math.log10(A_FORM_GAL), 4),
    "compression": False,
    "expansion_strength": 0.0,
    "anchor_a1": None,
    "anchor_scale_mpc": GALAXY_SCALE_MPC,
    "fond_layer": "localgroup",        # le poids de zoom milkyway est
                                       # reporté sur le fond localgroup
    "sprite_slug": "milkyway",
    "keyframes_a": [],                 # aucune frame propre à cuire
    "frame_pattern": None,
    "frame_resolution": None,
})

# ── Ligne A (14/07) : layer milkyway_hires — un layer de zoom = un visuel
# unique ; le disque VL détaillé 1024² est un layer à part entière, pas une
# ressource du layer milkyway. Frontière A/B (0.04 Mpc) ajustable.
hires = dict(layers[-1])          # copie du layer milkyway
hires["key"] = "milkyway_hires"
hires["max_mpc"] = 0.04
hires["sprite_slug"] = "milkyway_hires"
hires["comment"] = ("Ligne A (14/07) : disque Voie lactée détaillé 1024² + fond "
    "localgroup. Un layer de zoom = un visuel unique : le sprite hires N'EST PAS une "
    "ressource du layer milkyway mais un layer à part entière. Frontière A/B (0.04 Mpc) "
    "ajustable après retour visuel. Absent de layerWeights.ts production pour l'instant "
    "(zoom prototype).")
layers.append(hires)

matrix = {
    "version": 3,
    "generated": "2026-07-13",
    "comment": "SOURCE DE VÉRITÉ éditable — cf. docs/matrice-parametres-zoom-temps.md. "
               "Éditer ici puis relancer scripts/generate_spacetime_frames.py "
               "et scripts/dev/validate_spacetime_matrix.py.",
    "time_axis": {
        "a_min": round(1.0 / 1101.0, 8),      # recombinaison z≈1100, §3
        "a_max": 1.0,
        # Affichage : temps cosmique LINÉAIRE en milliards d'années (décision
        # du 13 juillet — l'ancien curseur log10(a) étalait l'embrasement,
        # t<38 Myr, sur 42% de la course). Les keyframes de génération
        # restent définies en a ; le mapping a<->t vient de la table
        # cosmologique (Planck, H0=67.4). Pas d'anamorphose.
        "display": {
            "mode": "cosmic_time_gyr_linear",
            "mapping_table": "data/cosmology_table.json",
            "t_min_gyr": T_MIN_GYR,
            "t_max_gyr": T_MAX_GYR,
            "readout": ["t_gyr", "z", "a"],
        },
    },
    "zoom_axis": {
        "halfwidth_min_mpc": 0.02,             # UniverseMap.tsx
        "halfwidth_max_mpc": 14570.0,
        # Frontières et largeurs de fondu entre layers — copie de
        # app/src/layerWeights.ts (LAYER_EDGES_MPC / FADE_WIDTHS_DEX).
        "layer_order": ["milkyway", "localgroup", "l1b", "l2", "l2b", "l3",
                        "l3b", "l4", "l4a", "l4b", "l5a", "l5"],
        "layer_edges_mpc": [0.1, 2.4, 8.49, 30, 67.08, 150, 212.13, 300,
                            793.73, 2100, 5531.46],
        "fade_widths_dex": [0.15, 0.52, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15,
                            0.15, 0.15, 0.15],
    },
    "galaxy_scale_mpc": GALAXY_SCALE_MPC,
    "embrasement": {   # §11.4.c — calibré le 10 juillet, inchangé
        "exp": 5, "offset_max": 18, "fade_scale_mpc": GALAXY_SCALE_MPC,
        "a_multiplier": 6,
    },
    # Effet d'expansion PAR ÉCHELLE (décision du 13 juillet, remplace
    # l'ancienne rampe globale lo=2/hi=15 qui violait le §11.4.e : force 0.66
    # à 8.5 Mpc -> "zoom" apparent sur le champ des 96 galaxies liées).
    # strength(hw) interpolé en smoothstep sur log10(s) entre les nœuds,
    # piloté par le demi-champ DEMANDÉ au curseur.
    # hw_eff = hw + (hw/a - hw) × strength(hw)
    "expansion": {
        "nodes": [[0.03, 0.0], [2.4, 0.0], [8.49, 0.15], [30.0, 0.65],
                  [67.08, 0.9], [150.0, 1.0], [14570.0, 1.0]],
        "comment": "≲2.4 Mpc lié (Groupe Local, aucun effet) ; 8.5 Mpc volume "
                   "local découplé (résiduel 0.15 validé) ; ≥150 Mpc flux de "
                   "Hubble pur — cf. §11.4.e",
    },
    "sprites": {   # rendu des galaxies par sprites N-corps CUITS (§11.5)
        # Correctif du 13 juillet : le prototype utilisait des splats de
        # particules bruts (points sans morphologie, flux conservé donc
        # jamais éteints) au lieu des 126 sprites cuits des sessions
        # précédentes. Désormais : frames pré-cuites uniquement.
        "frames_dir": "data/dissolution_sprites",
        "frame_pattern": "data/dissolution_sprites/{slug}_f{:02d}.png",
        "n_frames": 14,
        "frame_resolution": 512,    # sprites de dissolution (9 galaxies), 512²
        # progress = 1 − A_gal(a), frame = progress × 13 (interpolation
        # linéaire entre les deux frames encadrantes)
        "progress": "1 - A_sprite(a)  (bloc galaxy_formation, v3.3)",
        "fade_law": "A_sprite(a)^fade_exponent",
        # Extinction : contribution × A_gal(a)^fade_exponent — exposant 2 =>
        # les sprites se dissolvent DANS le fond AVANT que le fond (ancrages
        # à A_gal^1) ne se dissolve à son tour (séquencement validé 13/07).
        "fade_exponent": 2.0,
        "blend": "screen",              # §11.3 — jamais de fondu alpha temporel
        # Zone de visibilité : fondu en S sur le demi-champ EFFECTIF pour
        # éviter toute apparition brutale en zoomant.
        "visible_fade_band_mpc": [4.0, 6.0],
        # Plancher de lisibilité sur le CŒUR galactique (les naines sont
        # sous-pixel dès ~1 Mpc de demi-champ, et le cœur n'occupe que ~1/7
        # de la frame cadrée sur la dispersion finale -> aliasing) :
        # frame_half_px = max(physique, min_render_core_px × halfwidth_units).
        "min_render_core_px": 1.25,
        "min_render_comment": "Plancher de lisibilité sur le CŒUR galactique : la frame "
            "sprite est cadrée sur la dispersion finale (sprite_halfwidth_units ≈ 7-9 "
            "rayons), le cœur n'en occupe que ~1/7 ; un plancher sur la frame entière "
            "laisse le cœur sous-échantillonné (aliasing -> galaxie invisible). Rendu : "
            "frame_half_px = max(physique, min_render_core_px × sprite_halfwidth_units) "
            "=> le cœur couvre toujours ≥ ~2 px. Léger surdimensionnement des naines "
            "assumé.",
        "catalog_json": "data/local_group_catalog.json",
    },
    # Génération des sprites — chaîne complète (documentée dans la matrice
    # à la demande du 13 juillet ; provenance : sessions des 9-10 juillet) :
    "real_galaxies": {
        "generation": {
            "simulation": {
                "script": "scripts/simulate_dissolution.mjs",
                "engine": "N-corps Barnes-Hut, intégrateur leapfrog",
                "n_steps": 480, "n_keyframes": 14,
                "theta": 0.75, "softening": 0.018,
                "particles_per_galaxy": 2500,
                "initial_conditions": "morphologies GalaxyModel réelles + "
                                      "composantes de vitesse rotationnelles",
                "output": "data/dissolution_keyframes.json",
            },
            "baking": {
                "script": "scripts/generate_dissolution_sprites.mjs",
                "point_size": 0.5, "halo_growth": 8.5, "blur_max_px": 6,
                "filament_amount": 0.8,
                "tone_transform": "1 - exp(-champ)  (canal saturant, §11.3)",
                "framing": "demi-largeur = maxExtent(dernière frame) × 1.15, "
                           "FIXE pour toutes les frames d'une galaxie",
                "progress_per_frame": "f / 13 (linéaire)",
            },
        },
        # sprite_halfwidth_units = maxExtent(f13)×1.15 en unités de rayon
        # galactique (calculé depuis dissolution_keyframes.json) ;
        # sprite_halfwidth_mpc = × radiusMpc — demi-étendue MONDE du sprite.
        "entries": REAL_GALAXY_ENTRIES,
    },
    "layers": layers,
    # Rempli par generate_spacetime_frames.py après cuisson (valeurs de
    # normalisation figées + tons mesurés) — cf. §13.3 "figer la
    # normalisation une fois".
    "computed": None,
}

# ── Nomenclature des cellules (demande du 14 juillet) : <lettre><chiffre>,
# lettre = ligne de zoom (A = Voie lactée ... L = l5), chiffre = colonne de
# temps (0 = recombinaison ... 10 = aujourd'hui, linéaire en Gyr comme le
# curseur). Ex : C7 = vue l1b (8.49 Mpc) à t≈9.65 Ga.
_ORDER = ['milkyway_hires', 'milkyway', 'localgroup', 'l1b', 'l2', 'l2b',
          'l3', 'l3b', 'l4', 'l4a', 'l4b', 'l5a', 'l5']
_BY_KEY = {l['key']: l for l in layers}
_zoom_rows = {chr(ord('A') + i): {"layer": k, "halfwidth_mpc": _BY_KEY[k]['max_mpc']}
              for i, k in enumerate(_ORDER)}
def _a_of_t(t):
    rows = _COSMO
    if t <= rows[0]["t_Gyr"]:
        return rows[0]["a"]
    for i in range(len(rows) - 1):
        if rows[i]["t_Gyr"] <= t <= rows[i + 1]["t_Gyr"]:
            f = (t - rows[i]["t_Gyr"]) / (rows[i + 1]["t_Gyr"] - rows[i]["t_Gyr"])
            return rows[i]["a"] + (rows[i + 1]["a"] - rows[i]["a"]) * f
    return rows[-1]["a"]
_time_cols = {}
for _k in range(11):
    _t = T_MIN_GYR + _k / 10 * (T_MAX_GYR - T_MIN_GYR)
    _a = min(_a_of_t(_t), 1.0)
    _time_cols[str(_k)] = {"t_gyr": round(_t, 4), "a": round(_a, 6),
                           "z": round(1 / _a - 1, 4)}
matrix["nomenclature"] = {
    "format": "<lettre><chiffre> — la lettre identifie la LIGNE de zoom (un layer = un "
              "visuel unique = un code unique), le chiffre la COLONNE de temps (linéaire "
              "en Gyr). Ex : D7 = vue l1b (8.49 Mpc) à t≈9.65 Ga.",
    "zoom_rows": _zoom_rows,
    "time_columns": _time_cols,
    "comment": "13 lignes depuis le 14/07 (insertion de milkyway_hires en A, décalage "
               "unique des codes : l'ancien C (l1b) devient D, etc.). RÈGLE DE PERMANENCE : "
               "les lettres sont attribuées une fois pour toutes ; un layer inséré plus tard "
               "prend la première lettre libre suivante (N, O, ...) et c'est la table "
               "zoom_rows qui donne l'ordre de zoom, pas l'alphabet — un code désigne donc "
               "toujours le même visuel. A = Voie lactée détaillée, M = univers observable ; "
               "0 = recombinaison, 10 = aujourd'hui. Montage étiqueté avec ces codes.",
}

# ── Blocs de spécification v3 (14 juillet) — cuisson en attente
matrix["pending_generation"] = [
    "Recuisson v3.3 : textures density_l*.png + 114 frames st_* (Ψ comobile, α par frame à ton maintenu, fenêtre galaxies 0.75) — prévisualisation bande D..M avec verrou numérique (identité G10/Z2) avant gravure",
    "glow-test.html : vérification visuelle de calibration (inchangé)"
]
matrix["filamentarity"] = {
    "status": "REMPLACÉ le 16/07 par le bloc zeldovich (v3.2) — les crêtes multi-octaves produisaient de la mousse cellulaire, pas la toile de la référence. Conservé pour l'historique, ne JAMAIS cuire avec.",
    "stage": "Transformée 'ridged' appliquée au champ AVANT field_to_log_density, uniquement sur la composante passe-bande de longueur d'onde comobile < filament_max_scale_mpc ; les échelles supérieures restent gaussiennes.",
    "transform": "ridge = 1 - |2·norm(champ_bande) - 1|^ridge_exponent, mélangé au champ d'origine par ridge_mix ; renforcement HF spectral hf_boost ; assombrissement des vides void_gamma.",
    "filament_max_scale_mpc": 150.0,
    "physical_rationale": "Décision c du 14/07 : cohérence avec la réalité — la toile cosmique réelle n'a pas de filaments au-delà de ~100-150 Mpc comobiles. Aux lignes L/M (Gpc), la coupure passe-bande ne laisse subsister que de TOUT PETITS filaments (<1% du cadre) sur un fond statistiquement uniforme, sans structure filamenteuse à grande échelle.",
    "ridge_exponent": 1.5,
    "hf_boost": 0.25,
    "void_gamma": 1.5,
    "per_layer_ridge_mix_comment": "colonne filamentarity_ridge_mix de chaque layer GRF — valeurs de départ à calibrer (headless + retour visuel sur les cellules D10..M10)",
    "same_seeds": "Mêmes graines et mêmes phases que la génération actuelle — seule la transformation change, la toile reste la même.",
    "algorithm_v3_1": {
        "date": "15/07 — calibré par prévisualisation (preview_v3_iter2.py), validé auto-contrôles",
        "octaves": "Crêtes multi-octaves FIXES en espace pixel (périodes 128/32/8 px, poids 0.45/0.33/0.22), chaque octave intersectée avec la coupure physique k ≥ k(150 Mpc) — aux lignes L/M seules les octaves fines subsistent (uniformité + petits filaments automatiques). Octaves vides ignorées.",
        "ridge": "1 − |2·n01 − 1|^ridge_exponent, n01 = 0.5 + bande/(3.2σ) clampé [0,1]",
        "modulation": "Enveloppe de surdensité DÉCOUPLÉE de la coupure : sigmoïde 1/(1+exp(−2.2·low/σ_low)) sur la composante λ > monde/3 (héritée du parent — le Vide Local ~30 Mpc existe même dans le cadre l1b). mod = 0.25 + 0.75·env (env_mix 0.75). C'est elle qui sparsifie la toile (connectivité + crêtes hautes par kurtosis après renormalisation).",
        "ridge_gain": 2.6,
        "composition": "out = low + (1−ridge_mix)·high + ridge_mix·web·mod·σ_high·ridge_gain",
        "renormalisation": "OBLIGATOIRE : normalize_variance(out) avant field_to_log_density (la log-normale soustrait var/2, calibrée pour σ=1 — sans renormalisation la variance gonflée par les crêtes pénalise tout le champ : bogue attrapé en prévisualisation).",
        "anchored_layers": "global_suppression v2 (0.35 sur l1b, esthétique 'galaxies qui ressortent') passe à 1.0 en v3 : les galaxies siègent SUR la toile (nœuds), la dominance garantie des galaxies réelles s'adapte au niveau local du champ.",
        "gamma_calibre": 2.0
    }
}
matrix["zeldovich"] = {
    "status": "v3.3 SPÉCIFIÉ le 18/07 (retours Marc sur la v3.2 déployée) — recuisson en attente",
    "principle": "La cascade d'héritage FFT (mêmes graines, coarse 0.74 + detail 0.67) produit δ, INCHANGÉE. Densité = dépôt CIC d'une grille de masse advectée par le potentiel du champ : Ψ̂ = i·k·δ̂/k², les caustiques du flot forment les filaments (mécanisme physique réel de la toile).",
    "displacement_band": "Ψ limité à λ ∈ [lam_min_px, filament_max_scale_mpc comobiles] — la coupure 150 Mpc garantit l'uniformité aux lignes K/L/M (petits filaments seulement, décision c du 14/07).",
    "lam_min_px": 6,
    "filament_max_scale_mpc": 150.0,
    "s_px_a1": 11.0,
    "mass_grid": 1024,
    "deposit": "CIC (cloud-in-cell), périodique",
    "soft_px": 0.7,
    "exposure": {
        "formula": "t = (1 − exp(−α · ρ^shape))^void_gamma",
        "shape": 1.6,
        "void_gamma": 1.35,
        "target_mean_255": 38.0,
        "temporal_maintenance": "v3.3 (retour n°1 du 18/07) : α(s,a) est RÉSOLU PAR KEYFRAME pour que le ton moyen de chaque frame soit EXACTEMENT target_mean_255 — la luminosité moyenne est CONSERVÉE pendant la dissolution (la matière s'étale, la lumière ne disparaît pas). L'état dissous est donc un fond uni à 38/255 partagé par tous les layers (remplace l'α global v3.2 et son ton dissous 33/255 qui faisait passer les layers au noir avant l'embrasement). L'embrasement part de ce fond lumineux. Les α résolus sont stockés dans computed.per_layer_frames."
    },
    "temporal": {
        "formula": "S(s,a) = s_px_a1 × A(s,a)^q — Ψ ne change JAMAIS (mêmes phases), seule l'amplitude du déplacement suit la machinerie d'accrétion existante (a_form par layer). Les caustiques se dénouent continûment ; à S=0 la densité est EXACTEMENT uniforme.",
        "q": 1.0,
        "dissolved_tone": "(1 − exp(−α))^void_gamma — découle de la même formule à S=0 ; le plancher de convergence de C y est recalibré ; l'embrasement est inchangé. REMPLACE le ton dissous log-normal (129.4/255)."
    },
    "anchors": "Les bosses de galaxies (anchor_a1) sont injectées dans δ AVANT l'advection : le flot se connecte aux galaxies (nœuds-sur-brins). global_suppression = 1.0. La garantie « les vraies galaxies restent les maxima locaux » est re-validée en headless SUR LA DENSITÉ DÉPOSÉE. Amplitude des bosses × A_gal(a) comme avant.",
    "provenance": "preview_v3_iter4.py, variante Z2 (S=11, lam_min=6, sans halo ni scintillement), grille validée visuellement par Marc le 16/07.",
    "v3_3_coherence": {
        "problem": "v3.2 : Ψ renormalisé (rms=1) PAR LAYER -> les modes communs à deux zooms recevaient des amplitudes de déplacement différentes -> les caustiques ne s'effondraient pas aux mêmes endroits (structures 'changeantes' en zoomant, retour n°4 du 18/07).",
        "solution": "Ψ COMOBILE UNIQUE : plus aucune renormalisation par layer — Ψ = ∇∇⁻²δ tel quel (un même mode physique déplace la matière identiquement en Mpc comobiles à tous les zooms, l'héritage de δ garantit alors la cohérence inter-zoom par construction). L'amplitude est portée par un facteur de croissance G GLOBAL.",
        "growth_calibration": "G calibré pour que le déplacement rms de l3 (ligne G) soit 11 px — reproduit exactement la variante Z2 validée. Valeur stockée dans computed.zeldovich.",
        "consequences": "D/E un peu plus effondrés (déplacements comobiles plus grands en px aux petits cadres), K..M plus proches de l'uniforme (cohérent avec l'attente 'fond uni' du retour n°3).",
        "temporal": "G(s,a) = G × A(s,a)^q — même loi qu'avant, appliquée à G."
    }
}
matrix["galaxy_formation"] = {
    "status": "SPÉCIFIÉ le 18/07 — narration de condensation validée par Marc : brouillard -> nuages/filaments (a_form des layers de champ) -> les galaxies s'y CONDENSENT ensuite. (Le bottom-up cosmologique réel est sciemment écarté, décision réitérée.)",
    "a_form_sprites": 0.75,
    "halfwidth_dex": 0.1249,
    "center_dex": -0.1249,
    "window_a": [
        0.5625,
        1.0
    ],
    "drives": "A_sprite(a) pilote : progress et extinction des sprites (toutes galaxies, y compris milkyway_hires), amplitude des bosses d'ancrage injectées dans δ (lignes D/E), amplitude des galaxies procédurales de la texture C. L'EMBRASEMENT garde son propre calage (A_gal a_form=0.20, inchangé).",
    "comment": "Même forme de fenêtre (smoothstep en log a) que les layers. Valeur 0.75 ajustable après retour visuel."
}
matrix["prototype_rendering"] = {
    "status": "SPÉCIFIÉ le 18/07",
    "adaptive_canvas": "300 px pendant la manipulation des curseurs, raffinement à 640 px au repos (la pixelisation de la Voie lactée hires venait du canvas 300, pas des sprites 2048).",
    "minification": "Moyenne de zone (mip par blocs) quand la fenêtre minifie une texture — sans elle les petits filaments de K/L/M sont avalés par l'échantillonnage ponctuel (M paraissait uniforme/noir).",
    "ui_nomenclature": "Affichage permanent du code de ligne actif : 'D · l1b · 8.49 Mpc' (retour n°6 — les codes A..M sont la langue commune des retours)."
}
matrix["web_ambient"] = {
    "status": "Amplitudes relevées le 18/07 (0.12/0.20/0.35 -> 0.20/0.35/0.55 : invisibles à l'écran, mesuré ~+7/255 de structure). Ajustables.",
    "source_row": "D (l1b) : la toile ambiante de A/B/C est la texture de la ligne D échantillonnée sur la fenêtre courante. Même toile de part et d'autre de la frontière C/D → continuité automatique ; l'upsampling d'une petite région la rend naturellement très diffuse (aucun flou artificiel).",
    "blend": "screen (§11.3)",
    "amplitudes": {
        "milkyway_hires": 0.2,
        "milkyway": 0.35,
        "localgroup": 0.55
    },
    "temporal": "Suit les frames temporelles de la ligne D (même dissolution S(a)) — aucune cuisson propre, échantillonnage à l'affichage."
}
matrix["tone_mapping"] = {
    "status": "Intégré au bloc zeldovich.exposure le 16/07 (α global poolé D..M, cible 38/255 conservée) ; la cascade ton dissous + plancher C reste obligatoire, cf. zeldovich.temporal.dissolved_tone.",
    "problem": "Saut de ton moyen à la frontière C/D : localgroup ≈ 9/255, layers GRF ≈ 130/255 — aucune raison physique (problème n°2 du 14/07).",
    "target_mean_tone_255": [
        30,
        45
    ],
    "method": "Gain + gamma appliqués APRÈS la log-normale, avant la normalisation partagée figée. La chute de moyenne vient d'abord de la filamentarité (vides sombres + crêtes fines) ; le mapping ferme le reste de l'écart.",
    "cascade": "Le ton uniforme dissous partagé (129.4/255) ET le plancher de convergence localgroup (facteur 4.074) sont rescalés par le MÊME mapping — sinon les layers s'éclairciraient en se dissolvant. L'embrasement (additif, près de la recombinaison) est inchangé.",
    "validation": "Continuité du ton moyen mesurée à travers le fondu C/D à plusieurs temps (headless, avant tout retour visuel)."
}
matrix["field_evolution"] = {
    "status": "CUIT le 17/07 — loi S(s,a) appliquée aux 114 frames",
    "principle": "Une seule loi : S(s,a) = s_px_a1 × A(s,a)^q (cf. zeldovich.temporal). Le morphing entre keyframes interpole un même objet en déformation (mêmes phases) — §11.3 respecté par construction. Plus de lissage ni de relâchement de crêtes.",
    "keyframes": "Densité de keyframes à réévaluer aux zones de dénouement rapide (balayages denses de continuité, preuve de lissité).",
    "non_regression": "a=1 : A=1 → S=11 px = look Z2 validé."
}
matrix["real_galaxies"]["milkyway_hires"] = {
    "status": "CUIT le 17/07 — 14 frames 2048², corrélation f00/production vérifiée à la cuisson",
    "problem": "Les frames 512² sont cadrées sur la dispersion finale ×7.7 : le disque d'aujourd'hui n'occupe que ~70 px → bouillie floue au zoom maximal, sans commune mesure avec density_milkyway.png de production.",
    "script": "scripts/generate_milkyway_hires_sprites.py (Python, déterministe)",
    "source": "data/milkyway_dissolution_keyframes.json (simulation N-corps VL existante)",
    "resolution": 2048,
    "n_frames": 14,
    "framing_halfwidth_units": 2.0,
    "framing_comment": "Cadrage FIXE 2 rayons à 2048² : le disque occupe ~1024 px de large (pleine résolution écran téléphone, demande du 15/07). Débordement des frames de dispersion assumé (extinction A_gal² dominante à ce stade) + APODISATION cuite : fondu cosinus sur les derniers 6% du cadre (aucune coupure carrée possible).",
    "output": "data/dissolution_sprites_hires/milkyway_f00..f13.png",
    "f00_validation": "Corrélation exigée entre f00 et density_milkyway.png (contrôle headless ajouté à la cuisson).",
    "used_by_layer": "milkyway_hires (ligne A)",
    "runtime": "Mêmes lois que le bloc sprites : progress = 1−A_gal(a), extinction A_gal², mélange screen, plancher cœur.",
    "splats": "Par particule : sigma = sz × (résolution/1024) clampé [0.8, 6.0] px (champ 'sz' de particleMeta), amplitude 0.18 + b×0.55, ton 1−exp(−k·champ) avec k auto-calibré (p99.7 du champ non nul -> ton 0.95).",
    "sprite_halfwidth_mpc": 0.031887,
    "halo_growth": 2.5,
    "exposure": "k calibré sur f00 (p99.7 -> 0.95), PARTAGÉ par les 14 frames (continuité de flux)",
    "used_fade_band_mpc": [
        0.4,
        0.6
    ],
    "used_fade_comment": "Fondu de ZOOM (pas temporel, §11.3 respecté) entre le sprite 512 cadrage large (halo 7.7 rayons) et le hires (2 rayons) : poids hires = 1−smoothstep(log hw) sur la bande — évite le pop d'étendue visible au swap.",
    "sprite_halfwidth_units": 2.0
}

# ── Post-traitements v3.3 (18/07)
matrix["sprites"]["progress"] = "1 - A_sprite(a)  (bloc galaxy_formation, v3.3)"
matrix["sprites"]["fade_law"] = "A_sprite(a)^fade_exponent"
for _l in matrix["layers"]:
    _l.pop("zeldovich_s_px", None)          # v3.3 : G global, plus d'amplitude par layer
    if _l.get("anchor_a1"):
        _l["anchor_a1"]["global_suppression"] = 1.0
    if _l["key"] in matrix["web_ambient"]["amplitudes"]:
        _l["web_ambient_amplitude"] = matrix["web_ambient"]["amplitudes"][_l["key"]]

with open(OUT_PATH, "w") as f:
    json.dump(matrix, f, indent=1, ensure_ascii=False)

n_frames = sum(len(l["keyframes_a"]) for l in layers)
print(f"Matrice écrite -> {OUT_PATH}")
print(f"{len(layers)} layers temporels, {n_frames} frames à cuire")
for l in layers:
    print(f"  {l['key']:<11} s={l['max_mpc']:<8} a_form={l['a_form']:<6} "
          f"fenêtre a=[{l['dissolution_window_a'][0]:.4f}, 1] "
          f"{len(l['keyframes_a'])} keyframes")
