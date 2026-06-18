"""
native_oxide_model.py
─────────────────────
Yasaka/Morita layer-by-layer kinetic model for native SiO₂ growth.
Reference: Morita et al., J. Appl. Phys. 68, 1272 (1990).
 
ODEs
────
    dθₙ/dt = Kₙ · (θₙ₋₁ − θₙ)    n = 1 … N
    θ₀(t) ≡ 1   (H-passivated substrate, fully available)
    θₙ(0) = 0   for n ≥ 1
 
Rate-constant ansatz  [empirical self-limitation, NOT in Morita 1990]:
    Kₙ = K₁ · exp(−γ · (n−1))
 
Total oxide thickness:
    T_ox(t) = T₀ + d_mono · Σ θₙ(t)
 
Fitted parameters : K₁  [min⁻¹],  γ  [dimensionless],  d_mono  [Å]
Fixed             : T₀ = initial oxide from water-cleaning step
Scope             : n-Si(100) in air only.
                    n⁺-Si and p⁺-Si involve field-assisted (Cabrera–Mott)
                    oxidation that this model does not describe.
"""
 
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import differential_evolution, minimize
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
 
# ─────────────────────────────────────────────────────────────────────────────
# 1.  Digitised data  —  Morita et al. (1990), Figure 1
#
#     Reading uncertainty: ±0.1–0.2 Å vertical; ±5% in log time horizontal.
#     Hard anchor from Table I: n-Si in air (1.2 % H₂O) at 7 days = 10 080 min → 6.7 Å.
#     Explicit graph values from paper text: 5.4 Å and 7.6 Å plateaus.
# ─────────────────────────────────────────────────────────────────────────────
# n-Si(100), P-doped, 10¹⁵ cm⁻³  [model target]
t_nSi = np.array([1, 5, 20, 100, 400, 1000, 2000, 5000,
                   10080, 20000, 50000, 100000], dtype=float)
ox_nSi = np.array([1.9, 1.9, 1.9, 1.9, 2.1, 5.4, 5.4, 5.6,
                    6.7, 7.1, 7.4, 7.6], dtype=float)
 
# n⁺-Si(100), 10²⁰ cm⁻³  [field-assisted — Yasaka model inapplicable]
t_nplus  = np.array([1, 10, 50, 200, 700, 2000, 7000, 20000, 70000, 100000], dtype=float)
ox_nplus = np.array([4.4, 5.0, 5.8, 7.0, 8.2, 9.0, 9.8, 10.4, 10.8, 11.0], dtype=float)
 
# p⁺-Si(100), 10²⁰ cm⁻³
t_pplus  = np.array([1, 50, 300, 1000, 5000, 20000, 100000], dtype=float)
ox_pplus = np.array([2.3, 2.4, 2.7, 4.5, 6.0, 7.0, 7.8], dtype=float)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 2.  Kinetic model
# ─────────────────────────────────────────────────────────────────────────────
N_LAYERS = 6   # beyond layer 6 Kₙ is negligible for γ > 1.5
 
def K_arr(K1, gamma, N=N_LAYERS):
    return K1 * np.exp(-gamma * np.arange(N))
 
def ode_rhs(t, theta, K):
    """Vectorised RHS so Radau can exploit Jacobian structure."""
    dth    = np.empty_like(theta)
    dth[0] = K[0] * (1.0 - theta[0])
    for n in range(1, len(K)):
        dth[n] = K[n] * (theta[n-1] - theta[n])
    return dth
 
def integrate_layers(K1, gamma, t_eval, N=N_LAYERS):
    """Solve ODE, return θₙ(t)  shape (N, len(t_eval))."""
    K  = K_arr(K1, gamma, N)
    t0 = max(t_eval.min() * 1e-4, 1e-10)
    sol = solve_ivp(
        ode_rhs, (t0, t_eval.max()),
        y0     = np.zeros(N),
        t_eval = t_eval,
        args   = (K,),
        method = 'Radau',   # handles stiffness from K₁ ≫ Kₙ
        rtol=1e-11, atol=1e-14,
    )
    if not sol.success:
        raise RuntimeError(f"ODE failed: {sol.message}")
    return sol.y   # (N, len(t))
 
def T_model(K1, gamma, d_mono, T0, t_eval):
    return T0 + d_mono * integrate_layers(K1, gamma, t_eval).sum(axis=0)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 3.  Analytical closed-form solutions for θ₁ and θ₂  (cross-validation only)
# ─────────────────────────────────────────────────────────────────────────────
def theta1_exact(K1, t):
    return 1.0 - np.exp(-K1 * t)
 
def theta2_exact(K1, K2, t):
    eps = 1e-12 * (K1 + K2)
    if abs(K1 - K2) < eps:                        # degenerate equal rates
        return 1.0 - (1.0 + K1 * t) * np.exp(-K1 * t)
    # General solution (distinct rates):
    # θ₂(t) = 1 − [K₁·exp(−K₂t) − K₂·exp(−K₁t)] / (K₁ − K₂)
    return 1.0 - (K1 * np.exp(-K2 * t) - K2 * np.exp(-K1 * t)) / (K1 - K2)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 4.  Optimisation  —  fit K₁, γ, d_mono to n-Si(100) data
# ─────────────────────────────────────────────────────────────────────────────
T0 = 1.9   # Å — initial oxide grown during water-cleaning/drying step
 
def rmse_cost(log_params, t_data, ox_data):
    """Optimise log₁₀(K₁) to handle orders-of-magnitude range cleanly."""
    K1    = 10.0 ** log_params[0]
    gamma = log_params[1]
    dmono = log_params[2]
    if not (0.1 < gamma < 12.0 and 0.8 < dmono < 4.0):
        return 1e9
    try:
        pred = T_model(K1, gamma, dmono, T0, t_data)
        return float(np.sqrt(np.mean((pred - ox_data)**2)))
    except Exception:
        return 1e9
 
bounds = [(-7.0, -1.0),   # log₁₀(K₁)
          ( 0.2, 10.0),   # γ
          ( 0.8,  3.5)]   # d_mono [Å]
 
print("Phase 1 — global search (differential evolution)…")
res_de = differential_evolution(
    rmse_cost, bounds, args=(t_nSi, ox_nSi),
    seed=0, maxiter=8000, tol=1e-11, polish=True,
    mutation=(0.5, 1.5), recombination=0.9, workers=1,
    popsize=20
)
print(f"  DE   RMSE = {res_de.fun:.4f} Å   params = {res_de.x}")
 
print("Phase 2 — local refinement (Nelder–Mead)…")
res_nm = minimize(
    rmse_cost, res_de.x, args=(t_nSi, ox_nSi),
    method='Nelder-Mead',
    options={'xatol': 1e-13, 'fatol': 1e-13, 'maxiter': 1_000_000}
)
 
K1_opt    = 10.0 ** res_nm.x[0]
gam_opt   = res_nm.x[1]
dmono_opt = res_nm.x[2]
rmse_opt  = float(res_nm.fun)
K_opt     = K_arr(K1_opt, gam_opt)
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 5.  Report
# ─────────────────────────────────────────────────────────────────────────────
SEP = "=" * 62
print(f"\n{SEP}")
print("  FIT RESULTS — n-Si(100) in air   Morita 1990, Fig. 1")
print(SEP)
print(f"  K₁      = {K1_opt:.4e}  min⁻¹    (τ₁ = 1/K₁ = {1/K1_opt:.0f} min)")
for n in range(1, N_LAYERS):
    print(f"  K{n+1}      = {K_opt[n]:.4e}  min⁻¹    (τ  = {1/K_opt[n]:.0f} min)")
print(f"  γ       = {gam_opt:.4f}   (exponential rate attenuation per layer)")
print(f"  d_mono  = {dmono_opt:.4f}  Å    (monolayer step height)")
print(f"  T₀      = {T0:.2f}    Å    (fixed — initial water-grown oxide)")
print(f"  RMSE    = {rmse_opt:.4f}  Å    ({len(t_nSi)} digitised points)")
 
T_pred    = T_model(K1_opt, gam_opt, dmono_opt, T0, t_nSi)
residuals = T_pred - ox_nSi
mae_val   = float(np.mean(np.abs(residuals)))
max_err   = float(np.max(np.abs(residuals)))
print(f"  MAE     = {mae_val:.4f}  Å")
print(f"  MaxErr  = {max_err:.4f}  Å")
 
# Analytical cross-check
t_ck   = np.array([1000.0])
th_num = integrate_layers(K1_opt, gam_opt, t_ck)
th1_a  = theta1_exact(K_opt[0], 1000.0)
th2_a  = theta2_exact(K_opt[0], K_opt[1], 1000.0)
print()
print("  Numerical vs. closed-form cross-check at t = 1000 min:")
print(f"    θ₁  numerical = {th_num[0,0]:.8f}   exact = {th1_a:.8f}   |Δ| = {abs(th_num[0,0]-th1_a):.1e}")
print(f"    θ₂  numerical = {th_num[1,0]:.8f}   exact = {th2_a:.8f}   |Δ| = {abs(th_num[1,0]-th2_a):.1e}")
 
print()
print(f"  {'t (min)':>10}   {'T_Morita':>10}   {'T_model':>10}   {'Residual':>10}   flag")
print(f"  {'-'*56}")
for t_i, m_i, p_i in zip(t_nSi, ox_nSi, T_pred):
    flag = " ← >0.5 Å" if abs(p_i - m_i) > 0.5 else ""
    print(f"  {t_i:10.0f}   {m_i:10.2f}   {p_i:10.3f}   {p_i-m_i:10.3f}{flag}")
 
print(f"\n  Table I anchor check: T_model(10080 min) = {T_model(K1_opt, gam_opt, dmono_opt, T0, np.array([10080.]))[0]:.3f} Å   (Morita Table I = 6.7 Å)")
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 6.  Plots
# ─────────────────────────────────────────────────────────────────────────────
t_dense    = np.logspace(0, 5.05, 2000)
T_dense    = T_model(K1_opt, gam_opt, dmono_opt, T0, t_dense)
lyr_dense  = integrate_layers(K1_opt, gam_opt, t_dense)
 
fig, axes = plt.subplots(1, 3, figsize=(17, 5))
fig.patch.set_facecolor('white')
fig.suptitle(
    f"Yasaka/Morita layer-by-layer kinetics  —  n-Si(100) in air  —  Morita et al. (1990)\n"
    f"K₁={K1_opt:.2e} min⁻¹   γ={gam_opt:.2f}   d_mono={dmono_opt:.2f} Å   "
    f"RMSE={rmse_opt:.3f} Å   MAE={mae_val:.3f} Å",
    fontsize=10, y=1.01
)
 
# ── (A) Model fit + all three datasets ──────────────────────────────────────
ax = axes[0]
ax.semilogx(t_dense,  T_dense,   'C0-',  lw=2.5, zorder=3, label='Model (fit to n-Si)')
ax.semilogx(t_nSi,   ox_nSi,    'ko',   ms=9,   zorder=5, label='Morita n-Si  (10¹⁵)')
ax.semilogx(t_nplus, ox_nplus,  'C2^',  ms=7, alpha=0.70, label='Morita n⁺-Si (10²⁰)')
ax.semilogx(t_pplus, ox_pplus,  'C3s',  ms=7, alpha=0.70, label='Morita p⁺-Si (10²⁰)')
# Mark Table I anchor explicitly
ax.semilogx(10080, 6.7, 'C4D', ms=10, zorder=6, label='Table I anchor (7 d, 6.7 Å)')
ax.set(xlabel='TIME (min)', ylabel='OXIDE THICKNESS (Å)',
       title='(A)  Model vs. Morita 1990',
       xlim=(1, 1e5), ylim=(0, 12))
ax.legend(fontsize=8, loc='upper left')
ax.grid(True, which='both', alpha=0.2)
 
# ── (B) Individual layer contributions ──────────────────────────────────────
ax = axes[1]
cmap = plt.cm.plasma(np.linspace(0.1, 0.92, N_LAYERS))
for n in range(N_LAYERS):
    ax.semilogx(t_dense, lyr_dense[n] * dmono_opt,
                color=cmap[n], lw=1.8,
                label=f'Layer {n+1}  K={K_opt[n]:.1e} min⁻¹')
ax.semilogx(t_dense, lyr_dense.sum(axis=0) * dmono_opt,
            'k--', lw=1.6, label='Σ (net growth above T₀)')
ax.set(xlabel='TIME (min)', ylabel='Thickness contribution (Å)',
       title='(B)  Per-layer contributions × d_mono',
       xlim=(1, 1e5))
ax.legend(fontsize=7.5)
ax.grid(True, which='both', alpha=0.2)
 
# ── (C) Residuals ────────────────────────────────────────────────────────────
ax = axes[2]
ax.axhline(0, color='k', lw=0.9, ls='--')
ax.axhspan(-0.5, 0.5, alpha=0.12, color='steelblue', label='±0.5 Å (≈ digitisation noise)')
ax.semilogx(t_nSi, residuals, 'ro-', ms=9, lw=1.8, label='Residual = model − Morita')
for t_i, r_i in zip(t_nSi, residuals):
    if abs(r_i) > 0.4:
        ax.annotate(f'{r_i:+.2f} Å', (t_i, r_i),
                    textcoords='offset points', xytext=(5, 7),
                    fontsize=8, color='darkred')
ax.set(xlabel='TIME (min)',
       ylabel='T_model − T_Morita (Å)',
       title=f'(C)  Residuals   RMSE = {rmse_opt:.3f} Å   MAE = {mae_val:.3f} Å',
       xlim=(1, 1e5))
ax.legend(fontsize=9)
ax.grid(True, which='both', alpha=0.2)
 
plt.tight_layout()
out_png = '/mnt/user-data/outputs/morita_native_oxide_model.png'
plt.savefig(out_png, dpi=150, bbox_inches='tight')
plt.close()
print(f"\nPlot saved → {out_png}")
 



