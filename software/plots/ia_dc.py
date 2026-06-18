import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import linregress

# 1. Define your data arrays (Replace with your actual 4-point probe data)
v_in = np.array([0.005, 0.011, 0.015, 0.05, 0.1, 0.5, 0.75, 1.0]) # Example input voltages in volts
v_out_meas = np.array([0.05, 0.0229, 0.0332, 0.108, 0.195, 0.943, 1.498, 1.957]) # Example data with simulated error

ideal_gain = 2.0 # Target gain in V/V
v_out_ideal = v_in * ideal_gain

# 2. Mathematical Extraction of Error Metrics
# Perform linear regression to find actual operational slope and DC offset
slope, intercept, r_value, p_value, std_err = linregress(v_in, v_out_meas)

actual_gain = slope
offset_error_v = intercept
gain_error_pct = ((actual_gain - ideal_gain) / ideal_gain) * 100

# Absolute Error relative to ideal design
abs_error_v = v_out_meas - v_out_ideal

# Integral Non-Linearity (INL) relative to the actual best-fit operational line
v_out_fit = v_in * actual_gain + offset_error_v
inl_v = v_out_meas - v_out_fit
max_inl_v = np.max(np.abs(inl_v))
fsr_v = np.max(v_out_ideal) - np.min(v_out_ideal) # Full Scale Range
inl_pct_fsr = (max_inl_v / fsr_v) * 100

# Compile and export metrics
metrics = {
    "Target Gain (V/V)": round(ideal_gain, 3),
    "Actual Fit Gain (V/V)": round(actual_gain, 3),
    "Gain Error (%)": round(gain_error_pct, 3),
    "Offset Error (mV)": round(offset_error_v * 1000, 2),
    "Max INL (mV)": round(max_inl_v * 1000, 2),
    "Max INL (% FSR)": round(inl_pct_fsr, 3)
}

df_metrics = pd.DataFrame([metrics])
df_metrics.to_csv('software/plots/output/ia_dc/ia_dc_linearity_metrics.csv', index=False)
print(df_metrics.to_string(index=False))

# 3. Research-Grade Plot Formatting
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

# Single-panel, dual-y-axis layout: output voltage (left) + error in mV (right)
fig, ax1 = plt.subplots(figsize=(7, 4.8), dpi=300)
ax2 = ax1.twinx()

# Spread low-voltage region with logarithmic x scaling
ax1.set_xscale('log')

# Left y-axis: Transfer characteristic (Vout vs Vin)
line_ideal, = ax1.plot(v_in, v_out_ideal, color='black', linestyle='-', label=f'Ideal ($G={ideal_gain}$ V/V)')
line_meas, = ax1.plot(v_in, v_out_meas, color='#b22222', marker='o', linestyle='--', mfc='white', label='Measured Data')
ax1.set_xlabel(r"Input Voltage, $V_{in}$ (V)")
ax1.set_ylabel(r"Output Voltage, $V_{out}$ (V)")
ax1.grid(True, which='both', linestyle=':', alpha=0.6)

# Right y-axis: Absolute error profile (mV)
ax2.axhline(y=0, color='#0056b3', linestyle='-', lw=1.0, alpha=0.5)
line_err, = ax2.plot(v_in, abs_error_v * 1000, color='#0056b3', marker='s', linestyle='-', mfc='white', label='Absolute Error')
ax2.set_ylabel(r"Error (mV)", color='#0056b3')
ax2.tick_params(axis='y', labelcolor='#0056b3')

# Combined legend for both axes
lines = [line_ideal, line_meas, line_err]
labels = [line.get_label() for line in lines]
ax1.legend(lines, labels, loc='upper left', frameon=True, edgecolor='black')

# Annotate calculated offset and gain error away from the legend
ax1.text(0.62, 0.92, f'$V_{{os}} \\approx {offset_error_v*1000:.1f}$ mV\nGain Error $\\approx {gain_error_pct:.2f}$%',
         transform=ax1.transAxes, va='top',
         bbox=dict(facecolor='white', edgecolor='black', alpha=0.8))

plt.tight_layout()
plt.savefig('software/plots/output/ia_dc/ia_dc_transfer_analysis.png', format='png')