import os
import logging
from datetime import datetime
from sim import Esa

if 0:
    esa = Esa(4, 4)
    ps_n_bits = 4
else:
    esa = Esa(8, 8)
    ps_n_bits = 6
phase_step = 360 / (1 << ps_n_bits)


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
        s += f"v_rfdc"
        logging.info(f"{s}\n")

    def add_line(self, r, theta_d, phi_d):
        s = f"1, {r:.0f}, {theta_d:.0f}, {phi_d:.0f}"
        phases = esa.get_desired_phase(theta_d, phi_d)
        phases /= phase_step
        phases = phases.astype(int)
        for v in phases.flatten():
            s += f", {v}"
        s += f", {r * 10}"
        logging.info(f"{s}\n")


if __name__ == "__main__":
    gen = Generator()
    for r in range(50, 300 + 1, 100):
        for theta_d in range(0, 45 + 1, 10):
            for phi_d in range(180, 360 + 1, 60):
                phi_d = 0 if theta_d == 0 else phi_d
                gen.add_line(r, theta_d, phi_d)
                if theta_d == 0:
                    break