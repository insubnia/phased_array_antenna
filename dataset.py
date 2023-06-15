import os
import logging
import warnings
import numpy as np
from random import randint
from datetime import datetime
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
from sim import Esa

if 0:
    esa = Esa(4, 4)
    ps_n_bits = 4
else:
    esa = Esa(8, 8)
    ps_n_bits = 6
phase_step = 360 / (1 << ps_n_bits)
ps_code_limit = 1 << ps_n_bits

""" power per distance approximation
"""
warnings.filterwarnings('ignore')
xs = np.array([50, 100, 150, 200, 250, 300, 350, 400, 450, 500])
ys = np.array([1600, 950, 690, 600, 520, 435, 395, 365, 305, 260])
def func(xs, a, b, c):
    ys = a * np.exp(-b * xs) + c
    return ys
popt, pcov = curve_fit(func, xs, ys, p0=(2, 1e-2, 3))

def predict_power(d):
    return func(d, *popt)

if False:
    plt.plot(xs, ys, marker='.', label='real')
    ys2 = predict_power(xs)
    plt.plot(xs, ys2, marker='*', label='approximated')
    plt.legend()
    plt.grid()
    plt.show()


class Generator():
    def __init__(self):
        log_dir = './log'
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(filename=f"{log_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            filemode='w',
                            format='%(message)s',
                            datefmt='%y-%m-%d %H:%M:%S',
                            level=logging.INFO)
        logging.StreamHandler.terminator = ""
        s = "rx#, R, θ, φ"
        for i in range(esa.tx_num):
            s += f", ps#{i}"
        s += f", v_rfdc"
        logging.info(f"{s}\n")
        self.num_cases = 0

    def add_line(self, r, theta_d, phi_d):
        s = f"1, {r:.0f}, {theta_d:.0f}, {phi_d:.0f}"
        phases = esa.get_desired_phase(theta_d, phi_d)
        phases /= phase_step
        phases = phases.astype(int)
        power = predict_power(r + randint(-5, 5)) + randint(-10, 10)
        for v in phases.flatten():
            v = (v + randint(-4, 3)) % ps_code_limit
            s += f", {v}"
        s += f", {power:.0f}"
        logging.info(f"{s}\n")
        self.num_cases += 1


if __name__ == "__main__":
    gen = Generator()
    for r in range(50, 500 + 1, 50):
        for theta_d in range(0, 45 + 1, 5):
            for phi_d in range(180, 360 + 1, 5):
                if theta_d == 0: phi_d = 0
                gen.add_line(r, theta_d, phi_d)
                if theta_d == 0: break
    print(f"\nNumber of total cases: {gen.num_cases}")