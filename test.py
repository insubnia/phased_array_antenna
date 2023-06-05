import numpy as np

r, theta_d, phi_d = 0, 0, 0

def convert_coord(r, theta_d, phi_d):
    ''' d, h, a_d
    '''
    theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)
    d = r * np.sqrt(np.sin(theta_r)**2 * np.cos(phi_r)**2 + np.cos(theta_r)**2)
    h = r * np.sin(theta_r) * np.sin(phi_r)
    a_r = np.arctan(np.tan(theta_r) * np.cos(phi_r))
    a_d = np.rad2deg(a_r)
    return d, h, a_d


r = 100
for theta_d in range(0, 90 + 1, 10):
    for phi_d in range(180, 360 + 1, 30):
        d, h, a = convert_coord(r, theta_d, phi_d)
        print(f"r: {r:3.0f}, θ: {theta_d:3.0f}, φ: {phi_d:3.0f}  →  d: {d:4.2f}, h: {h:4.2f}, a: {a:4.2f}")
    print()


R = range(50, 300 + 1, 100)
THETA_D = range(0, 45 + 1, 10)
PHI_D = range(180, 360 + 1, 60)

dim3 = np.zeros((len(R), len(THETA_D), len(PHI_D)), dtype='O')
for i, r in enumerate(R):
    for j, theta_d in enumerate(THETA_D):
        for k, phi_d in enumerate(PHI_D):
            dim3[i][j][k] = (r, theta_d, phi_d)
print(dim3)
print(dim3.flatten())


if __name__ == "__main__":
    ...