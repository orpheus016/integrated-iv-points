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

# Style configuration for formal research dissemination
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "lines.linewidth": 1.5,
    "lines.markersize": 5
})

fig, ax1 = plt.subplots(figsize=(8, 5), dpi=300)

# Generate a secondary independent y-axis sharing the same x-axis
ax2 = ax1.twinx()

# Explicit color assignment to link traces directly to their respective axes
color_error = '#0056b3'    # Muted Blue
color_current = '#b22222'  # Firebrick Red

prev_r = 0
for i, reg in enumerate(regions):
    r_max = reg["r_max"]
    i_ideal = reg["i_ideal"]
    r_samp = reg["r_samples"]
    i_meas = reg["i_measured"]
    
    # 1. Plot Ideal Targets and Boundaries on the Right Axis (mA)
    ax2.hlines(y=i_ideal, xmin=prev_r, xmax=r_max, colors='black', linestyles='-', lw=1.2, label='Ideal Target' if i==0 else "")
    ax2.axvline(x=r_max, color='gray', linestyle='--', alpha=0.4, lw=0.8)
    
    # 2. Plot Experimental Current on the Right Axis (mA)
    ax2.plot(r_samp, i_meas, color=color_current, marker='o', linestyle='-', mfc='white', mew=1.5, label='Measured Current' if i==0 else "")
    
    # 3. Calculate and Plot Relative Error on the Left Axis (%)
    error_pct = ((i_meas - i_ideal) / i_ideal) * 100
    ax1.plot(r_samp, error_pct, color=color_error, marker='s', linestyle='--', mfc='white', mew=1.5, label='Relative Error' if i==0 else "")
    
    prev_r = r_max

# Horizontal reference for zero-deviation condition
ax1.axhline(y=0, color='gray', linestyle=':', lw=1)

# Left Axis (Relative Error) Customization
ax1.set_ylabel("Relative Error (%)", color=color_error)
ax1.tick_params(axis='y', labelcolor=color_error)
ax1.set_ylim(-20, 80)

# Right Axis (Output Current) Customization
ax2.set_ylabel(r"Output Current, $I_{out}$ (mA)", color='black')
ax2.tick_params(axis='y', labelcolor='black')
ax2.set_ylim(0, 26)

# Shared Base X-Axis Customization
ax1.set_xlabel(r"Load Resistance, $R_L$ ($\Omega$)")
boundary_ticks = [0] + [reg["r_max"] for reg in regions]
ax1.set_xticks(boundary_ticks)
ax1.set_xticklabels([f"{x:.1f}" for x in boundary_ticks])
ax1.set_xlim(0, max(boundary_ticks) * 1.05)
ax1.grid(True, which='major', linestyle=':', alpha=0.5)

# Unified Legend formatting to handle multi-axis entries without duplication
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', frameon=True, edgecolor='black')

plt.tight_layout()
plt.savefig('software/plots/output/current_source_consistency/current_source_consistency_plot_integrated.png')