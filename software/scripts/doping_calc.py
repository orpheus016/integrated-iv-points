import math

def calculate_silicon_doping(V, I, thickness_cm, temp_c, error_correction, type='n'):
    # Constants
    q = 1.602e-19
    T = temp_c + 273.15
    s = 0.127 # cm, probe spacing

    if thickness_cm < (0.127/2):    
    # 1. Calculate measured resistivity from 4-point probe
        rho = (V / I) * thickness_cm * error_correction
        sigma = 1 / rho
    
    elif thickness_cm > (0.127/2):
        rho = (V / I) * math.pi * thickness_cm / math.log(math.sinh(thickness_cm / s) / math.sinh(thickness_cm / (2 * s)))
        sigma = 1 / rho

    
    # 2. Set constants to match PV Education / Standard Si values
    if type.lower() == 'n':
        mu_max, mu_min = 1417.0, 52.2
        N_ref, alpha = 9.68e16, 0.68
    else:
        mu_max, mu_min = 470.5, 44.9
        N_ref, alpha = 2.23e17, 0.719

    # 3. Apply Temperature Correction (Arora Model)
    # Most PV data is normalized to 300K, so we adjust back
    t_norm = T / 300.0
    mu_max_t = mu_max * (t_norm**-2.5)
    mu_min_t = mu_min * (t_norm**-0.5)

    # 4. Iterative Solver to find N
    n_guess = 1e15 # Initial guess
    for i in range(30):
        # Calculate mobility at current doping guess
        mu = mu_min_t + (mu_max_t - mu_min_t) / (1 + (n_guess / N_ref)**alpha)
        # Update doping guess
        n_guess = sigma / (q * mu)
        
    return n_guess, rho

# Example:
#4m,8m,12m,20m
#voltage = 1.73V - 2.121mV
#sample voltage = 0.002 0.02 0.1 1.2
voltage = 0.99667846/2.02
current = 4
temperature = 22
thickness = 0.0375
error_correction = 3.00889 # usually its 4.532 but considering the edgecorrection factor and especiallly F2=0.78, it came down to this much
# assume the probe is perpendicular to the edge of non conductive barrier with distance = 1mm

doping, resistivity = calculate_silicon_doping(voltage, current / 1000, thickness, temperature, error_correction, 'n')
print(f"Doping: {doping:.5e} cm^-3")
print(f"Resistivity: {resistivity:.4f} Ohm-cm")
print(f"Sheet Resistance: {resistivity/thickness:.4f} Ohm/Sq")