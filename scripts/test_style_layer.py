"""
Test de style — génère UN champ de densité (layer "Toile cosmique", ~300 Mpc
de côté) et le rend dans deux styles visuels distincts pour comparaison.

Méthode (cf. document d'architecture §4.3) :
  1. Spectre de puissance P(k) via approximation BBKS (transfert CDM standard).
  2. Champ gaussien aléatoire en espace de Fourier, contraint par P(k).
  3. Transformation log-normale pour des densités positives.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from scipy.ndimage import gaussian_filter

# --- Paramètres cosmologiques (Planck 2018) ---
OMEGA_M = 0.315
H = 0.674
NS = 0.965
GAMMA = OMEGA_M * H  # paramètre de forme approché (BBKS, sans suppression baryonique)

N = 512               # résolution de la grille
BOX_MPC = 300.0       # côté de la boîte, en Mpc comobiles (échelle "Toile cosmique")
SEED = 42


def bbks_transfer(k_h_mpc):
    """Fonction de transfert BBKS (k en h/Mpc)."""
    q = np.maximum(k_h_mpc, 1e-8) / GAMMA
    return (np.log(1 + 2.34 * q) / (2.34 * q)) * (
        1 + 3.89 * q + (16.1 * q) ** 2 + (5.46 * q) ** 3 + (6.71 * q) ** 4
    ) ** -0.25


def power_spectrum(k_h_mpc):
    T = bbks_transfer(k_h_mpc)
    P = (k_h_mpc ** NS) * T ** 2
    P[k_h_mpc == 0] = 0
    return P


def generate_density_field(n=N, box_mpc=BOX_MPC, seed=SEED, sigma_target=1.0):
    rng = np.random.default_rng(seed)

    # Grille de nombres d'onde (en h/Mpc), convention rfft2
    d = box_mpc / n
    kx = np.fft.fftfreq(n, d=d) * 2 * np.pi
    ky = np.fft.rfftfreq(n, d=d) * 2 * np.pi
    kx_grid, ky_grid = np.meshgrid(kx, ky, indexing="ij")
    k_mag = np.sqrt(kx_grid ** 2 + ky_grid ** 2)

    P = power_spectrum(k_mag)

    # Champ gaussien complexe en Fourier, amplitude sqrt(P(k)), phases aléatoires
    noise_real = rng.normal(size=k_mag.shape)
    noise_imag = rng.normal(size=k_mag.shape)
    delta_k = (noise_real + 1j * noise_imag) * np.sqrt(P / 2.0) * n

    field = np.fft.irfft2(delta_k, s=(n, n))

    # Normalisation à une variance cible (proxy simplifié de sigma8)
    field = field / field.std() * sigma_target

    # Transformation log-normale : densités positives, cohérent avec les
    # statistiques réelles de la matière à grande échelle (cf. §4.3)
    density = np.exp(field - field.var() / 2.0)
    return density


def render_sober(density, path):
    """Style 1 : scientifique sobre — niveaux de bleu/blanc, façon carte de densité réelle."""
    cmap = LinearSegmentedColormap.from_list(
        "sober", ["#03040a", "#0a1a3a", "#2a5aa0", "#8fc7ff", "#f2f8ff"]
    )
    log_density = np.log10(density + 0.05)
    vmin, vmax = np.percentile(log_density, [2, 99.5])

    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    ax.imshow(log_density, cmap=cmap, vmin=vmin, vmax=vmax, origin="lower")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(path, facecolor="#03040a")
    plt.close(fig)


def render_contrasted(density, path):
    """Style 2 : contrasté / artistique — façon nébuleuse, avec un léger glow sur les filaments."""
    cmap = LinearSegmentedColormap.from_list(
        "nebula", ["#020009", "#1a0a3a", "#5a1a8a", "#c02a7a", "#ff8a3a", "#fff2b0"]
    )
    log_density = np.log10(density + 0.05)
    vmin, vmax = np.percentile(log_density, [1, 99.8])
    norm = np.clip((log_density - vmin) / (vmax - vmin), 0, 1)

    # Halo/glow : version floutée additionnée pour faire "briller" les filaments denses
    glow = gaussian_filter(np.clip(norm - 0.55, 0, None), sigma=4)
    combined = np.clip(norm + glow * 1.4, 0, 1)

    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    ax.imshow(combined, cmap=cmap, vmin=0, vmax=1, origin="lower")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(path, facecolor="#020009")
    plt.close(fig)


def render_astro(density, path):
    """Style 3 : imagerie astronomique — noir profond, matière en brun/orangé/blanc,
    avec de petits points lumineux façon étoiles/galaxies aux pics de densité."""
    cmap = LinearSegmentedColormap.from_list(
        "astro", ["#000000", "#170a05", "#4a1f0a", "#a8480f", "#e8a13a", "#fff3d6"]
    )
    log_density = np.log10(density + 0.05)
    vmin, vmax = np.percentile(log_density, [3, 99.9])
    norm = np.clip((log_density - vmin) / (vmax - vmin), 0, 1)

    # Légère texture de "poussière" pour casser l'uniformité des zones sombres
    rng = np.random.default_rng(7)
    dust = rng.normal(0, 0.015, size=norm.shape)
    norm = np.clip(norm + dust, 0, 1)

    rgba = cmap(norm)
    rgb = rgba[:, :, :3]

    # Points lumineux ponctuels aux pics locaux de densité (façon étoiles/galaxies)
    from scipy.ndimage import maximum_filter
    local_max = (density == maximum_filter(density, size=6)) & (density > np.percentile(density, 99.2))
    ys, xs = np.where(local_max)
    star_layer = np.zeros(norm.shape)
    star_layer[ys, xs] = 1.0
    star_glow = gaussian_filter(star_layer, sigma=0.8) * 3.0
    star_glow = np.clip(star_glow, 0, 1)

    for c in range(3):
        rgb[:, :, c] = np.clip(rgb[:, :, c] + star_glow * (1.0 if c != 2 else 0.85), 0, 1)

    fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
    ax.imshow(rgb, origin="lower")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(path, facecolor="#000000")
    plt.close(fig)


if __name__ == "__main__":
    density = generate_density_field()
    render_sober(density, "/mnt/user-data/outputs/style_sobre.png")
    render_contrasted(density, "/mnt/user-data/outputs/style_contraste.png")
    render_astro(density, "/mnt/user-data/outputs/style_astro.png")
    print("Densité générée : min", density.min(), "max", density.max(), "moyenne", density.mean())
    print("Images sauvegardées.")
