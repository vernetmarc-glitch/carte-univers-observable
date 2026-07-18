"""
Génère les champs de densité pour les layers 2 à 5 (le layer 1, local, n'est
pas procédural — cf. document d'architecture §4.1).

Méthode d'héritage entre échelles (cf. §4.3-4.4) : construction en champs
EMBOÎTÉS. Le layer le plus grand (L5) est généré en premier ; chaque layer
plus fin est ensuite obtenu en combinant :
  - une "tendance grossière" héritée : la région centrale du layer parent,
    recadrée puis suréchantillonnée (spline) à la résolution du layer fils ;
  - un "détail fin" nouveau : un champ gaussien frais, filtré en passe-haut
    pour ne garder que les fréquences que le layer parent ne pouvait pas
    représenter (au-delà de sa fréquence de Nyquist physique).

Ainsi, le layer fils "précise" statistiquement le layer parent au lieu de
lui être indépendant — exactement l'exigence d'héritage du projet.
"""

import numpy as np
from PIL import Image
from scipy.ndimage import zoom as ndi_zoom, gaussian_filter
from generate_local_group_catalog import build_catalog
from local_group_style import (
    REAL_GALAXY_HALO_SIGMA_MPC,
    REAL_GALAXY_NOISE_SUPPRESSION,
    REAL_GALAXY_SUPPRESSION_RADIUS_FACTOR,
    REAL_GALAXY_DOMINANT_AMPLITUDE_FACTOR,
    GALAXY_BRIGHTNESS_AMPLITUDE,
)

OMEGA_M = 0.315
H = 0.674
NS = 0.965
GAMMA = OMEGA_M * H

N = 1024  # marge de securite supplementaire, en plus du fix DPR cote app

# Marge de sécurité : les textures sont générées avec une étendue physique
# plus grande que leur frontière "logique" (utilisée pour le poids des layers
# et les labels), pour permettre un recadrage RECTANGULAIRE (au ratio de
# l'écran, portrait ou paysage) sans jamais dépasser les bords de l'image,
# même au zoom maximal. 1.5 couvre confortablement un ratio d'écran jusqu'à
# 1.5:1 (la plupart des tablettes/ordinateurs) ; les téléphones très
# allongés (~2:1 en portrait) peuvent garder un très léger letterboxing
# uniquement au zoom maximal absolu.
MARGIN_FACTOR = 1.5

# L5 est le SEUL layer visible pile à son bord extrême (le zoom maximal absolu
# de toute la carte) — c'est là que le letterboxing apparaissait sur les
# écrans de téléphone très allongés (~2,17:1). Les autres layers ont toujours
# une marge de manœuvre car on quitte leur plage avant d'atteindre leur bord.
# Une marge dédiée plus large, réservée à L5, couvre large sans pénaliser la
# résolution des autres layers.
MARGIN_FACTOR_L5 = 2.4

def margin_for(key):
    return MARGIN_FACTOR_L5 if key == "l5" else MARGIN_FACTOR

def box_mpc(max_mpc, margin=MARGIN_FACTOR):
    """Étendue physique réellement générée (avec marge), en Mpc, côté total."""
    return 2 * max_mpc * margin

# (clé, demi-largeur en Mpc comobiles, seed, parent) — de la plus grande à la
# plus petite échelle. "l4b", "l5a", "l4a", "l3b", "l2b", "l1b" sont des
# paliers TECHNIQUES intermédiaires (pas de nouveaux layers scientifiques —
# les 5 layers du document d'architecture restent les mêmes).
#
# IMPORTANT — parent EXPLICITE (pas l'élément précédent de la liste) :
# chaque palier hérite de son plus proche ANCÊTRE DE LA CHAÎNE SCIENTIFIQUE
# D'ORIGINE (l5, l4b, l4, l3, l2), pas du palier précédent. Ça évite que la
# chaîne d'héritage s'allonge démesurément quand on double le nombre de
# layers : sans ça, un layer comme L3 se serait retrouvé à la génération 6
# au lieu de 3, diluant ~97% de la structure à grande échelle héritée de L5
# (constaté et corrigé le 6 juillet — cf. document d'architecture).
LAYER_SPECS = [
    {"key": "l5", "max_mpc": 14570.0, "seed": 42, "parent": None},
    {"key": "l5a", "max_mpc": 5531.46, "seed": 48, "parent": "l5"},
    {"key": "l4b", "max_mpc": 2100.0, "seed": 55, "parent": "l5"},
    {"key": "l4a", "max_mpc": 793.73, "seed": 61, "parent": "l4b"},
    {"key": "l4", "max_mpc": 300.0, "seed": 101, "parent": "l4b"},
    {"key": "l3b", "max_mpc": 212.13, "seed": 108, "parent": "l4"},
    {"key": "l3", "max_mpc": 150.0, "seed": 102, "parent": "l4"},
    {"key": "l2b", "max_mpc": 67.08, "seed": 112, "parent": "l3"},
    {"key": "l2", "max_mpc": 30.0, "seed": 103, "parent": "l3"},
    {"key": "l1b", "max_mpc": 8.49, "seed": 117, "parent": "l2"},
]


def bbks_transfer(k_h_mpc):
    q = np.maximum(k_h_mpc, 1e-8) / GAMMA
    return (np.log(1 + 2.34 * q) / (2.34 * q)) * (
        1 + 3.89 * q + (16.1 * q) ** 2 + (5.46 * q) ** 3 + (6.71 * q) ** 4
    ) ** -0.25


def power_spectrum(k_h_mpc):
    T = bbks_transfer(k_h_mpc)
    P = (k_h_mpc ** NS) * T ** 2
    P[k_h_mpc == 0] = 0
    return P


def k_grid(n, box_mpc):
    d = box_mpc / n
    kx = np.fft.fftfreq(n, d=d) * 2 * np.pi
    ky = np.fft.rfftfreq(n, d=d) * 2 * np.pi
    kx_grid, ky_grid = np.meshgrid(kx, ky, indexing="ij")
    return np.sqrt(kx_grid ** 2 + ky_grid ** 2)


def generate_raw_field(n, box_mpc, seed, highpass_k=None):
    """Champ gaussien contraint par P(k), avec filtrage passe-haut optionnel
    (masque sigmoïde lisse pour éviter les artefacts de coupure nette)."""
    rng = np.random.default_rng(seed)
    k_mag = k_grid(n, box_mpc)
    P = power_spectrum(k_mag)

    if highpass_k is not None:
        # Masque sigmoïde en log(k), centré sur highpass_k (transition sur ~0.5 dex)
        with np.errstate(divide="ignore"):
            log_ratio = np.log10(np.maximum(k_mag, 1e-8) / highpass_k)
        mask = 1 / (1 + np.exp(-log_ratio / 0.15))
        P = P * mask

    noise_real = rng.normal(size=k_mag.shape)
    noise_imag = rng.normal(size=k_mag.shape)
    delta_k = (noise_real + 1j * noise_imag) * np.sqrt(P / 2.0) * n
    field = np.fft.irfft2(delta_k, s=(n, n))
    return field


def crop_and_upsample(parent_field, parent_max_mpc, child_max_mpc, n, parent_margin, child_margin):
    """Recadre la région centrale du champ parent correspondant à l'étendue
    du layer fils, puis suréchantillonne (spline cubique) à la résolution n.

    Généralisé pour accepter des marges DIFFÉRENTES entre parent et enfant
    (cf. MARGIN_FACTOR_L5) : la fraction à recadrer doit être calculée sur
    les étendues physiques réelles (max_mpc * marge), pas seulement le
    rapport des max_mpc logiques, sous peine de recadrer la mauvaise portion.
    """
    frac = (child_max_mpc * child_margin) / (parent_max_mpc * parent_margin)
    crop_size = max(int(round(n * frac)), 4)
    start = (n - crop_size) // 2
    crop = parent_field[start:start + crop_size, start:start + crop_size]
    zoom_factor = n / crop_size
    upsampled = ndi_zoom(crop, zoom_factor, order=3)
    # ndi_zoom peut légèrement dévier de n x n selon les arrondis : on rectifie
    upsampled = upsampled[:n, :n]
    if upsampled.shape != (n, n):
        pad = n - upsampled.shape[0]
        upsampled = np.pad(upsampled, ((0, pad), (0, pad)), mode="edge")
    return upsampled


def normalize_variance(field, target=1.0):
    std = field.std()
    return field / std * target if std > 0 else field


def field_to_log_density(field):
    return np.log10(np.exp(field - field.var() / 2.0) + 0.05)


def export_layer_png(log_density, vmin, vmax, path):
    norm = np.clip((log_density - vmin) / (vmax - vmin), 0, 1)
    img_data = (norm * 255).astype(np.uint8)
    Image.fromarray(img_data, mode="L").save(path)


def value_noise_field(n, grid_size, seed):
    """Bruit de valeur (grille aléatoire grossière + interpolation smoothstep),
    identique en esprit à valueNoiseField() dans
    app/public/l1b-anchor-test.html — utilisé pour les "nuages interstellaires"
    entre les galaxies réelles sur l1b (cf. apply_local_group_anchor).
    Volontairement différent du champ gaussien à spectre BBKS des autres
    layers : ce n'est pas de la structure cosmologique, juste une texture de
    fond plausible entre des objets connus.
    """
    rng = np.random.default_rng(seed)
    g = max(2, round(grid_size))
    grid = rng.random((g + 1, g + 1)) * 2 - 1

    ys = np.linspace(0, g, n, endpoint=False)
    xs = np.linspace(0, g, n, endpoint=False)
    gy0 = np.clip(np.floor(ys).astype(int), 0, g - 1)
    gx0 = np.clip(np.floor(xs).astype(int), 0, g - 1)
    fy = ys - np.floor(ys)
    fx = xs - np.floor(xs)
    sy = fy * fy * (3 - 2 * fy)
    sx = fx * fx * (3 - 2 * fx)

    v00 = grid[gy0[:, None], gx0[None, :]]
    v10 = grid[gy0[:, None], gx0[None, :] + 1]
    v01 = grid[gy0[:, None] + 1, gx0[None, :]]
    v11 = grid[gy0[:, None] + 1, gx0[None, :] + 1]
    a = v00 + (v10 - v00) * sx[None, :]
    b = v01 + (v11 - v01) * sx[None, :]
    return a + (b - a) * sy[:, None]


def build_structured_anchor_field(catalog, max_mpc, n, size_multiplier=2.2, bump_amplitude_factor=1.0):
    """Construit un champ 2D avec, pour chaque galaxie du catalogue, un halo
    gaussien large + un point central compact.

    Taille/amplitude importées de local_group_style.py (SOURCE UNIQUE pour
    les galaxies réelles — cf. ce fichier pour le pourquoi). HALO_SCALE et
    CORE_SCALE restent volontairement faibles ici (pas dans le module
    partagé, propres à ce pipeline de normalisation par percentiles) : le
    rendu KDE en direct (app/src/kdeRender.ts) normalise différemment
    (par frame), donc réutiliser ses valeurs saturerait cette texture-ci.

    SIZE_MPC est un PLANCHER relatif à la résolution du layer courant, pas
    une valeur absolue fixe : REAL_GALAXY_HALO_SIGMA_MPC (0.05 Mpc) est
    calibré pour l1b (~0.025 Mpc/px, soit ~2px de sigma), mais devient
    sub-pixel dès qu'on l'applique tel quel à un layer plus grossier (ex.
    l2 : ~0.088 Mpc/px -> sigma < 1px -> pic invisible après recolorisation,
    cf. diagnostic du 6 juillet). Le max() garantit un pic toujours visible,
    quel que soit le layer où l'ancrage est appliqué.

    `size_multiplier` : par défaut 2.2 (le plancher minimal pour rester
    visible). Une valeur plus grande (cf. l1b en mode "suppression globale",
    7 juillet) donne des taches plus larges et douces, nécessaire quand plus
    aucun bruit ambiant ne reste autour pour donner une impression de volume.

    `bump_amplitude_factor` : calibré via app/public/l1b-anchor-test.html
    (7 juillet) — multiplicateur direct sur l'amplitude des pics.
    """
    AMPLITUDE = GALAXY_BRIGHTNESS_AMPLITUDE
    HALO_SCALE = 0.12
    CORE_SCALE = 0.35

    pixel_size_mpc = box_mpc(max_mpc) / n
    SIZE_MPC = max(REAL_GALAXY_HALO_SIGMA_MPC, pixel_size_mpc * size_multiplier)
    core_sigma_mpc = pixel_size_mpc * 1.3
    yy, xx = np.indices((n, n))
    cx, cy = n / 2, n / 2
    x_mpc = (xx - cx) * pixel_size_mpc
    y_mpc = (yy - cy) * pixel_size_mpc

    field = np.zeros((n, n))
    for gal in catalog:
        angle_rad = np.radians(gal["angleDeg"])
        gx = np.cos(angle_rad) * gal["distanceMpc"]
        gy = np.sin(angle_rad) * gal["distanceMpc"]
        peak_amp = np.log(1 + gal["brightness"] * AMPLITUDE) * bump_amplitude_factor
        field += HALO_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * SIZE_MPC ** 2))
        field += CORE_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * core_sigma_mpc ** 2))
    return field, x_mpc, y_mpc, SIZE_MPC, AMPLITUDE


def apply_local_group_anchor(
    field,
    max_mpc,
    n,
    catalog,
    strength=1.0,
    global_suppression=1.0,
    size_multiplier=2.2,
    real_only=True,
    cloud_amplitude=0.0,
    cloud_scale=18,
    extra_blur_px=0.0,
    bump_amplitude_factor=1.0,
    diffuse=False,
):
    """Ajoute les bosses de densité du catalogue PAR-DESSUS le champ aléatoire
    existant, avec un traitement RENFORCÉ pour les galaxies RÉELLES :

    Diagnostic (constaté visuellement + vérifié numériquement) : la
    contribution de l'ancrage au pic (~0.6) était bien plus faible que
    l'amplitude typique du bruit aléatoire ambiant (pics fréquents de 1 à 3,
    le champ étant normalisé à variance ~1). Résultat : les maxima de
    densité visibles ne correspondaient pas aux vraies positions des
    galaxies réelles (rendues en points sur le layer Groupe Local juste en
    dessous) — l'alignement visuel entre les deux layers n'était pas garanti.

    Correctif historique (6 juillet) : pour les galaxies RÉELLES uniquement
    PAR DÉFAUT, on ATTÉNUE localement le bruit ambiant autour de leur
    position, puis on y superpose une bosse d'amplitude largement dominante
    — garantissant que le maximum local de densité coïncide avec la vraie
    position de la galaxie. Constantes importées de local_group_style.py.

    `strength` (0-1) : l'ancrage plein (1.0, l1b) n'a de sens que sur le
    layer qui REND ces galaxies individuellement visibles juste en dessous.
    Sur l2, simple TRACE (0.4) pour une transition douce.

    `real_only` : build_catalog() contient 8 galaxies réelles + ~90
    procédurales — real_only=False (l1b) traite l'ensemble.

    `diffuse` (ajouté le 7 juillet, deuxième itération) : le mode
    "dominance forcée" ci-dessus (suppression locale + bosse garantie
    maximale) donne des ronds nets qui ressemblent à des autocollants posés
    sur le champ, pas à une vraie sur-densité cosmique — constaté aussi
    après une première tentative avec un bruit de "nuages" fabriqué à la
    main (cloud_amplitude), qui ne ressemblait pas du tout à la texture
    filamenteuse réelle de l2 (même moyenne/écart-type, mais une structure
    spatiale bien plus lisse/en tâches que la vraie texture multi-échelle).
    En mode diffuse : le champ naturel hérité de l2 (déjà généré par LE
    MÊME moteur que l2, cf. main()) n'est presque pas touché
    (global_suppression proche de 1), aucune suppression locale de bruit ni
    bosse "garantie dominante" — juste un halo doux ADDITIONNÉ par-dessus,
    qui se fond dans la texture existante au lieu de la remplacer.
    """
    structured_target, x_mpc, y_mpc, size_mpc, amplitude = build_structured_anchor_field(
        catalog, max_mpc, n, size_multiplier=size_multiplier, bump_amplitude_factor=bump_amplitude_factor
    )
    cloud = value_noise_field(n, cloud_scale, seed=2002) if cloud_amplitude > 0 else 0.0
    result = field * global_suppression + cloud * cloud_amplitude + structured_target * strength

    if not diffuse:
        suppression_mask = np.ones((n, n))
        dominant_bumps = np.zeros((n, n))
        SUPPRESSION_RADIUS_MPC = size_mpc * REAL_GALAXY_SUPPRESSION_RADIUS_FACTOR
        noise_suppression = 1 - (1 - REAL_GALAXY_NOISE_SUPPRESSION) * strength
        dominant_factor = REAL_GALAXY_DOMINANT_AMPLITUDE_FACTOR * strength * bump_amplitude_factor

        for gal in catalog:
            if real_only and not gal["isReal"]:
                continue
            angle_rad = np.radians(gal["angleDeg"])
            gx = np.cos(angle_rad) * gal["distanceMpc"]
            gy = np.sin(angle_rad) * gal["distanceMpc"]
            dist2 = (x_mpc - gx) ** 2 + (y_mpc - gy) ** 2

            # Attenuation locale du bruit (cf. REAL_GALAXY_NOISE_SUPPRESSION dans
            # local_group_style.py pour le niveau d'attenuation au centre)
            local_dip = 1 - (1 - noise_suppression) * np.exp(-dist2 / (2 * SUPPRESSION_RADIUS_MPC ** 2))
            suppression_mask *= local_dip

            peak_amp = np.log(1 + gal["brightness"] * amplitude)
            dominant_bumps += dominant_factor * peak_amp * np.exp(-dist2 / (2 * size_mpc ** 2))

        result = result * suppression_mask + dominant_bumps

    if extra_blur_px > 0.3:
        result = gaussian_filter(result, sigma=extra_blur_px)
    return result


def main():
    fields = {}
    specs_by_key = {s["key"]: s for s in LAYER_SPECS}

    # Poids rééquilibrés (idée n°1) : 55% de la variance vient désormais du
    # parent hérité (contre ~31% avant), le reste du détail neuf — au lieu de
    # renormaliser à variance 1 avec des poids qui diluaient la structure
    # héritée de génération en génération. Combiné à l'héritage direct depuis
    # l'ancêtre scientifique (idée n°2, cf. "parent" dans LAYER_SPECS), la
    # structure à grande échelle de L5 se propage beaucoup mieux à tous les
    # paliers (cf. document d'architecture pour le calcul complet).
    W_COARSE = 0.74
    W_DETAIL = 0.67

    for spec in LAYER_SPECS:
        margin = margin_for(spec["key"])
        parent_key = spec["parent"]

        if parent_key is None:
            field = generate_raw_field(N, box_mpc(spec["max_mpc"], margin), spec["seed"])
            field = normalize_variance(field)
        else:
            parent_spec = specs_by_key[parent_key]
            parent_field = fields[parent_key]
            parent_margin = margin_for(parent_key)
            coarse_trend = crop_and_upsample(
                parent_field, parent_spec["max_mpc"], spec["max_mpc"], N, parent_margin, margin
            )
            k_transition = np.pi * N / box_mpc(parent_spec["max_mpc"], parent_margin)
            detail = generate_raw_field(
                N, box_mpc(spec["max_mpc"], margin), spec["seed"], highpass_k=k_transition
            )
            field = normalize_variance(coarse_trend) * W_COARSE + normalize_variance(detail) * W_DETAIL

        if spec["key"] == "l1b":
            # 7 juillet, 3e itération : variante "H — sprite adouci"
            # choisie par l'utilisateur parmi 10 aperçus générés côté chat
            # (cf. scripts non versionnés ayant servi à ces aperçus). Fond
            # nettement assombri entre les galaxies (comme le layer sprite
            # juste en dessous), mais avec des taches PLUS PETITES et
            # légèrement adoucies plutôt que les gros ronds nets de la
            # toute première itération (6 juillet) — diffuse=False
            # (mécanisme "pic garanti dominant" + suppression locale du
            # bruit, cf. docstring apply_local_group_anchor), avec
            # size_multiplier et bump_amplitude_factor réduits + un léger
            # flou (extra_blur_px) pour casser la dureté des bords.
            # real_only=False : le layer Groupe Local en dessous montre les
            # 98 galaxies du catalogue (8 réelles + ~90 procédurales), pas
            # seulement les 8 nommées.
            catalog = build_catalog()
            field = apply_local_group_anchor(
                field,
                spec["max_mpc"],
                N,
                catalog,
                strength=1.0,
                # v3.2 (16/07) : les galaxies siègent SUR la toile de
                # Zel'dovich — plus de suppression ambiante (la dominance
                # garantie des galaxies réelles s'adapte au niveau local).
                global_suppression=1.0,
                size_multiplier=1.8,
                real_only=False,
                bump_amplitude_factor=0.50,
                extra_blur_px=0.6,
                diffuse=False,
            )
        elif spec["key"] == "l2":
            # "Trace" (cf. docstring apply_local_group_anchor) : l2 est le
            # layer suivant dans l'ordre du zoom (l1b -> l2), pas un enfant
            # de l1b dans la hiérarchie d'héritage (c'est l'inverse : l1b
            # hérite DE l2, cf. LAYER_SPECS) — sans cet appel explicite, l2
            # n'a strictement aucune connaissance des positions réelles et
            # les pics disparaissent net à la frontière l1b/l2 (diagnostic
            # du 6 juillet).
            #
            # 7 juillet, 4e itération (portée décidée avec l'utilisateur
            # après discussion sur le sens de l'héritage, cf. doc §4.4 —
            # l'héritage du champ ALÉATOIRE reste bien grand->petit, on ne
            # fait ici que propager la contrainte LOCALE du Groupe Local,
            # de façon volontairement bornée à l1b/l2/l2b) : real_only=False
            # et diffuse=True pour rester cohérent avec le traitement de
            # l1b (catalogue complet, look vaporeux) plutôt que l'ancien
            # traitement "8 galaxies, pic dur" d'origine.
            catalog = build_catalog()
            field = apply_local_group_anchor(
                field,
                spec["max_mpc"],
                N,
                catalog,
                strength=1.6,
                real_only=False,
                diffuse=True,
                size_multiplier=5.0,
                bump_amplitude_factor=2.6,
            )
        elif spec["key"] == "l2b":
            # 7 juillet, 4e itération : trace encore plus atténuée qu'l2
            # (strength plus bas) pour que la transition l2 -> l2b ne fasse pas
            # disparaître net les mêmes 98 positions (même défaut que celui
            # corrigé entre l1b et l2, cf. diagnostic du 6 juillet).
            # DÉLIBÉRÉMENT LA DERNIÈRE ÉTAPE de cette propagation : au-delà
            # de l2b (~67 Mpc), le Groupe Local doit redevenir
            # statistiquement invisible — rien ne nous distingue à cette
            # échelle (principe cosmologique, cf. doc §4.1 ligne 5), y
            # ajouter une trace créerait un artefact fixe au centre de la
            # carte à des échelles où il n'a scientifiquement pas lieu
            # d'être.
            #
            # 7 juillet, 5e itération : strength/bump_amplitude_factor
            # remontés sur l2 ET l2b (retour utilisateur — la trace était
            # devenue quasi invisible sur l2, le fond naturel de ce layer
            # étant beaucoup plus bruité que celui de l1b, ~3x l'écart-type,
            # noyait complètement le pic précédent). l2b reste
            # volontairement plus faible que l2 pour garder un fondu
            # progressif plutôt qu'un plateau.
            catalog = build_catalog()
            field = apply_local_group_anchor(
                field,
                spec["max_mpc"],
                N,
                catalog,
                strength=0.85,
                real_only=False,
                diffuse=True,
                size_multiplier=5.0,
                bump_amplitude_factor=1.7,
            )

        fields[spec["key"]] = field

    # --- v3.2 (16/07, matrice bloc `zeldovich`, variante Z2 validée) ---
    # La densité n'est plus la log-normale du champ : c'est le dépôt CIC
    # d'une grille de masse advectée par le potentiel du champ (caustiques =
    # filaments). L'exposition α est GLOBALE, calibrée en pooling (rôle de
    # l'ancienne normalisation partagée), et stockée dans matrix.computed
    # pour que les frames temporelles utilisent EXACTEMENT la même.
    import zeldovich_engine as ze

    psis = {}
    for spec in LAYER_SPECS:
        world = box_mpc(spec["max_mpc"], margin_for(spec["key"]))
        psis[spec["key"]] = ze.displacement(fields[spec["key"]], world)
    growth = ze.calibrate_growth(psis["l3"])       # reproduit la Z2 validée
    computed = ze.store_computed(growth)
    print(f"v3.3 : G={growth:.4f} (rms l3 = 11 px), ton maintenu "
          f"{computed['target_mean_255']}/255")
    rhos = {k: ze.density_from_psi(psis[k], growth, N) for k in psis}

    for spec in LAYER_SPECS:
        out_path = f"../app/public/data/density_{spec['key']}.png"
        a_k = ze.solve_alpha(rhos[spec["key"]])    # ton maintenu par layer (v3.3)
        ze.export_tone_png(ze.tone(rhos[spec["key"]], a_k), out_path)
        print(f"{spec['key']} -> {out_path} (alpha={a_k:.3f})")


if __name__ == "__main__":
    main()
