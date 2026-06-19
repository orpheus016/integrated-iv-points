import math

def calculate_silicon_doping(V, I, thickness_cm, temp_c, type='n'):
    # Constants
    q = 1.602e-19
    T = temp_c + 273.15
    s = 0.127
    
    # 1. Calculate measured resistivity from 4-point probe
    rho = (V / I) * thickness_cm * 4.532
    sigma = 1 / rho
    
    if thickness_cm < (0.127/2):    
    # 1. Calculate measured resistivity from 4-point probe
        rho = (V / I) * thickness_cm * 4.532
        sigma = 1 / rho
    
    else:
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
doping, resistivity = calculate_silicon_doping((0.96/2)*0.78*0.66, 0.004, 0.05, 26.85, 'n')
print(f"Doping: {doping:.3e} cm^-3")
print(f"Resistivity: {resistivity:.4f} Ohm-cm")