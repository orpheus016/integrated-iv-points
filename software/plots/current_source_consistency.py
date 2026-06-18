import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# Define data based on the provided values
regions = [
    {"r_max": 12.7553, "i_ideal": 20.0, "r_samples": np.array([2.7 , 11]), "i_measured": np.array([24.2, 23])},
    {"r_max": 35.6846, "i_ideal": 12.0, "r_samples": np.array([13, 22, 35]), "i_measured": np.array([16.99, 15.64, 19.87])},
    {"r_max": 70.9224, "i_ideal": 8.0,  "r_samples": np.array([38.5, 49, 70]), "i_measured": np.array([ 8.65, 8.47, 8.45])},
    {"r_max": 236.380, "i_ideal": 4.0,  "r_samples": np.array([82, 120, 164, 182, 200, 210, 220]), "i_measured": np.array([6.71, 5.79, 4.79, 4.69, 3.95, 4.02, 4.37])}
]

# 1. Calculate metrics
results = []
for i, reg in enumerate(regions):
    i_meas = reg["i_measured"]
    i_ideal = reg["i_ideal"]
    
    mean_i = np.mean(i_meas)
    std_i = np.std(i_meas, ddof=1) # Sample standard deviation
    cv = (std_i / mean_i) * 100    # Coefficient of Variation
    load_reg = (np.max(i_meas) - np.min(i_meas)) / i_ideal * 100 # Load Regulation
    
    results.append({
        "Target Current (mA)": i_ideal,
        "Max Resistance (Ohm)": reg["r_max"],
        "Mean (mA)": round(mean_i, 3),
        "Std Dev (mA)": round(std_i, 3),
        "CV (%)": round(cv, 2),
        "Load Regulation (%)": round(load_reg, 2)
    })

df_metrics = pd.DataFrame(results)
df_metrics.to_csv('software/plots/output/current_source_consistency/stability_metrics.csv', index=False)

# 2. Research-grade plot formatting
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 12,
    "axes.titlesize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "lines.linewidth": 1.5,
    "lines.markersize": 5
})

# Create a 2-panel plot (Absolute Values Top, Percentage Error Bottom)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), dpi=300, sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

prev_r = 0
for i, reg in enumerate(regions):
    r_max = reg["r_max"]
    i_ideal = reg["i_ideal"]
    r_samp = reg["r_samples"]
    i_meas = reg["i_measured"]
    
    # Top Plot: Absolute Values
    ax1.hlines(y=i_ideal, xmin=prev_r, xmax=r_max, colors='black', linestyles='-', lw=1.5, label='Ideal Target' if i==0 else "")
    ax1.axvline(x=r_max, color='gray', linestyle='--', alpha=0.5, lw=1)
    ax1.plot(r_samp, i_meas, color='#b22222', marker='o', linestyle='-', mfc='white', mew=1.5, label='Measured' if i==0 else "")
    
    # Bottom Plot: Percentage Error relative to Ideal
    error_pct = ((i_meas - i_ideal) / i_ideal) * 100
    ax2.axhline(y=0, xmin=prev_r, xmax=r_max, color='black', linestyle='-', lw=1.5)
    ax2.axvline(x=r_max, color='gray', linestyle='--', alpha=0.5, lw=1)
    ax2.plot(r_samp, error_pct, color='#0056b3', marker='s', linestyle='--', mfc='white', mew=1.5)
    
    prev_r = r_max

# Formatting Top Axis
ax1.set_ylabel(r"Output Current, $I_{out}$ (mA)")
ax1.grid(True, which='major', linestyle=':', alpha=0.6)
ax1.legend(loc='upper right', frameon=True, edgecolor='black')
ax1.set_ylim(0, 26)

# Formatting Bottom Axis
ax2.set_ylabel(r"Relative Error (%)")
ax2.set_xlabel(r"Load Resistance, $R_L$ ($\Omega$)")
ax2.grid(True, which='major', linestyle=':', alpha=0.6)

# Custom X-ticks mapped strictly to operational boundaries
boundary_ticks = [0] + [reg["r_max"] for reg in regions]
ax2.set_xticks(boundary_ticks)
ax2.set_xticklabels([f"{x:.1f}" for x in boundary_ticks])
ax2.set_xlim(0, max(boundary_ticks) * 1.05)

plt.tight_layout()
plt.savefig('software/plots/output/current_source_consistency/research_grade_stability_plot.png')