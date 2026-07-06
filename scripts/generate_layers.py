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
from scipy.ndimage import zoom as ndi_zoom
from generate_local_group_catalog import build_catalog

OMEGA_M = 0.315
H = 0.674
NS = 0.965
GAMMA = OMEGA_M * H

N = 512  # résolution commune à tous les layers

# (clé, demi-largeur en Mpc comobiles, seed) — de la plus grande à la plus petite échelle.
# "l4b" est un palier technique intermédiaire (pas un 6e layer scientifique) ajouté
# uniquement pour que le ratio d'échelle entre deux textures consécutives reste
# raisonnable (le saut direct L4->L5, ratio 48.6x, produisait un recadrage à
# seulement ~10 px sources — bien trop pixelisé pour un fondu propre).
LAYER_SPECS = [
    {"key": "l5", "max_mpc": 14570.0, "seed": 42},
    {"key": "l4b", "max_mpc": 2100.0, "seed": 55},
    {"key": "l4", "max_mpc": 300.0, "seed": 101},
    {"key": "l3", "max_mpc": 150.0, "seed": 102},
    {"key": "l2", "max_mpc": 30.0, "seed": 103},
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


def crop_and_upsample(parent_field, parent_max_mpc, child_max_mpc, n):
    """Recadre la région centrale du champ parent correspondant à l'étendue
    du layer fils, puis suréchantillonne (spline cubique) à la résolution n."""
    frac = child_max_mpc / parent_max_mpc
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


def build_structured_anchor_field(catalog, max_mpc, n):
    """Construit un champ 2D avec, pour chaque galaxie du catalogue, un halo
    gaussien large + un point central compact.

    Attention : ces constantes sont volontairement DIFFÉRENTES (bien plus
    faibles) que celles du rendu KDE en direct (app/src/kdeRender.ts). Les
    deux pipelines de normalisation ne sont pas les mêmes : le rendu JS
    normalise dynamiquement par frame, alors que L2 est normalisé une fois
    pour toutes par percentiles partagés entre tous les layers (cf. main()).
    Réutiliser les mêmes valeurs qu'en JS sature une grande zone ici (halos
    proches superposés) car cette normalisation-ci les laisse s'accumuler.
    Le rôle de cet ancrage est mineur (continuité de second ordre, la
    transition principale est gérée par le fondu de poids avec le layer
    Groupe Local) — pas besoin de reproduire l'intensité exacte du direct.
    """
    SIZE_MPC = 0.59
    AMPLITUDE = 3.5
    HALO_SCALE = 0.12     # tres reduit par rapport au rendu JS (0.85) : evite la saturation
    CORE_SCALE = 0.35     # idem (JS: 2.5)

    pixel_size_mpc = (2 * max_mpc) / n
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
        peak_amp = np.log(1 + gal["brightness"] * AMPLITUDE)
        field += HALO_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * SIZE_MPC ** 2))
        field += CORE_SCALE * peak_amp * np.exp(-((x_mpc - gx) ** 2 + (y_mpc - gy) ** 2) / (2 * core_sigma_mpc ** 2))
    return field


def apply_local_group_anchor(field, max_mpc, n, catalog):
    """Ajoute les bosses de densité du catalogue PAR-DESSUS le champ aléatoire
    existant (additif). Le rôle de cet ancrage est désormais réduit : la
    frontière Groupe Local/L2 calibrée est à 2.4 Mpc (cf. layerWeights.ts),
    bien en-deçà de l'étendue du catalogue (jusqu'à 10 Mpc) — cet ancrage ne
    sert plus qu'à une continuité de second ordre au-delà de la frontière.
    """
    structured_target = build_structured_anchor_field(catalog, max_mpc, n)
    return field + structured_target


def main():
    fields = {}
    prev_spec = None
    prev_field = None

    for spec in LAYER_SPECS:
        if prev_field is None:
            field = generate_raw_field(N, 2 * spec["max_mpc"], spec["seed"])
            field = normalize_variance(field)
        else:
            coarse_trend = crop_and_upsample(
                prev_field, prev_spec["max_mpc"], spec["max_mpc"], N
            )
            k_transition = np.pi * N / (2 * prev_spec["max_mpc"])
            detail = generate_raw_field(
                N, 2 * spec["max_mpc"], spec["seed"], highpass_k=k_transition
            )
            field = normalize_variance(coarse_trend) * 0.6 + normalize_variance(detail) * 0.9

        if spec["key"] == "l2":
            catalog = build_catalog()
            field = apply_local_group_anchor(field, spec["max_mpc"], N, catalog)

        fields[spec["key"]] = field
        prev_spec = spec
        prev_field = field

    # --- Normalisation PARTAGÉE entre tous les layers ---
    # (au lieu d'une normalisation par percentiles propre à chaque layer, qui
    # provoquait un désalignement de contraste/luminosité au moment du fondu
    # entre deux layers adjacents).
    log_densities = {k: field_to_log_density(f) for k, f in fields.items()}
    pooled = np.concatenate([ld.ravel() for ld in log_densities.values()])
    vmin, vmax = np.percentile(pooled, [1, 99.7])
    print(f"Normalisation partagee : vmin={vmin:.3f} vmax={vmax:.3f}")

    for spec in LAYER_SPECS:
        out_path = f"../app/public/data/density_{spec['key']}.png"
        export_layer_png(log_densities[spec["key"]], vmin, vmax, out_path)
        print(f"{spec['key']} (max {spec['max_mpc']} Mpc) -> {out_path}")


if __name__ == "__main__":
    main()
