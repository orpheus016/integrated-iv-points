import matplotlib.pyplot as plt
import numpy as np

# Data extracted from logs
reference_voltage = 0.43300
measured_voltages = [
    0.43350100, 0.43370428, 0.43341932, 0.43360414, 0.43347477, 0.43354330,
    0.43364820, 0.43354034, 0.43366789, 0.43343486, 0.43363571, 0.43346166,
    0.43357968, 0.43368458, 0.43345808, 0.43374834, 0.43346047, 0.43363037,
    0.43363752, 0.43357791, 0.43378171, 0.43344078, 0.43363690, 0.43345632,
    0.43374896, 0.43350400, 0.43377218, 0.43345632, 0.43373703, 0.43369412,
    0.43356952, 0.43374896, 0.43338003, 0.43365120, 0.43346462, 0.43361663
]

# Calculations
samples = np.arange(1, len(measured_voltages) + 1)
mean_voltage = np.mean(measured_voltages)

# Plot configuration for IEEE-style clarity (high contrast, distinct markers)
plt.figure(figsize=(10, 6), dpi=300)

# Plotting elements
plt.scatter(samples, measured_voltages, color='#1f77b4', marker='o', s=40, label='Measured Values', zorder=3)
plt.axhline(y=reference_voltage, color='#d62728', linestyle='-', linewidth=2, label=f'True Reference ({reference_voltage:.5f} V)', zorder=2)
plt.axhline(y=mean_voltage, color='#2ca02c', linestyle='--', linewidth=2, label=f'Mean Measurement ({mean_voltage:.5f} V)', zorder=2)

# Axes and formatting
plt.xlabel('Sample Number', fontsize=12, fontweight='bold')
plt.ylabel('Voltage (V)', fontsize=12, fontweight='bold')
plt.title('ADC Voltage Metrology: Precision vs. Accuracy Offset', fontsize=14)

# Force the Y-axis to clearly frame both the reference and the measured cluster
plt.ylim(0.4328, 0.4340)

plt.grid(True, linestyle=':', alpha=0.7, zorder=1)
plt.legend(loc='upper right', framealpha=1.0, edgecolor='black')
plt.tight_layout()

# Save the figure
plt.savefig('adc_metrology_analysis.png')
plt.show()