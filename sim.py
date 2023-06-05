#!/home/sis/.pyenv/shims/python3
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# constants
c = 3e11

# parameters
Fin = 5.8e9
Ampl = 8

# dependencies
wave_length = c / Fin
k = 2 * np.pi / wave_length  # wavenumber
dx = wave_length / 2
dy = wave_length / 2

""" Coordinate transformation
"""
def u(theta_r, phi_r):
    return np.sin(theta_r) * np.cos(phi_r)

def v(theta_r, phi_r):
    return np.sin(theta_r) * np.sin(phi_r)

def spherical_to_cartesian(r, theta_r, phi_r):
    x = r * u(theta_r, phi_r)
    y = r * v(theta_r, phi_r)
    z = r * np.cos(theta_r)
    return x, y, z

""" Plotting constants
"""
DEGREE_STEP = 5
_THETA = np.arange(-90, 90 + 1, DEGREE_STEP)
_PHI = np.arange(-180, 180 + 1, DEGREE_STEP)
THETA, PHI = np.deg2rad(np.meshgrid(_THETA, _PHI))


class Esa():
    def __init__(self, M, N):
        self.M, self.N = M, N
        self.theta0_d, self.phi0_d = 0, 0
        self.phases = np.zeros((self.N, self.M), dtype=float)

        self.weights = np.full((self.N, self.M), Ampl)
        self.xms = np.arange(0.5 - self.M / 2, self.M / 2, 1) * dx
        self.yns = np.arange(0.5 - self.N / 2, self.N / 2, 1) * dy
        self.yns = np.flip(self.yns)

    def set_target_angle(self, theta_d, phi_d):
        self.theta0_d, self.phi0_d = theta_d, phi_d

    def set_phases(self, phases_d):
        self.phases = phases_d

    @property
    def tx_num(self):
        return self.M * self.N

    def set_amplitude(self, amplitude):
        self.weights.fill(amplitude)

    def get_vector(self, phases):
        class _Vector():
            def __init__(self, theta, phi):
                self.theta = theta
                self.phi = phi
        pattern_data = self.get_pattern_data_by_phased_array(phases)
        idx = np.unravel_index(np.argmax(pattern_data, axis=None), pattern_data.shape)
        theta, phi = np.rad2deg(THETA[idx]), np.rad2deg(PHI[idx])

        # positive number conversion
        if theta == 0:
            phi = 0
        elif theta < 0:
            phi += 180
        else:
            phi += 360
        theta, phi = abs(theta), phi % 360

        return _Vector(theta, phi)

    def get_pattern_data_by_target_angle(self, theta_d, phi_d):
        theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)
        u0, v0 = u(theta_r, phi_r), v(theta_r, phi_r)
        r = np.zeros(np.shape(PHI))
        for n, yn in enumerate(self.yns):
            for m, xm in enumerate(self.xms):
                r = r + self.weights[n][m] * np.exp(1j * (
                    k * (xm * (u(THETA, PHI) - u0) + yn * (v(THETA, PHI) - v0))
                ))
        return abs(r)

    def get_pattern_data_by_phased_array(self, phase_d):
        phase = np.deg2rad(phase_d)
        r = np.zeros(np.shape(PHI))
        for n, yn in enumerate(self.yns):
            for m, xm in enumerate(self.xms):
                r = r + self.weights[n][m] * np.exp(1j * (
                    k * (xm * u(THETA, PHI) + yn * v(THETA, PHI)) +
                    phase[n][m]
                ))
        return abs(r)

    def get_desired_phase(self, theta_d, phi_d):
        theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)
        phase_d = np.ndarray((self.N, self.M))
        for n, yn in enumerate(self.yns):
            for m, xm in enumerate(self.xms):
                cmplx = np.exp(-1j * k * (xm * u(theta_r, phi_r) + yn * v(theta_r, phi_r)))
                phase_d[n][m] = np.angle(cmplx, deg=True)
        return phase_d

    def plot(self):
        fig = plt.figure()
        fig.subplots_adjust(left=.03, right=.97)

        self.ax = fig.add_subplot(projection='3d')
        self.ax.set_title("Beam Pattern", color='#778899', size=15, weight='bold', va='bottom')
        self.ax.view_init(elev=110, azim=-105, roll=-15)
        self.ax.xaxis.set_ticklabels([])
        self.ax.yaxis.set_ticklabels([])
        self.ax.zaxis.set_ticklabels([])

        R = self.get_pattern_data_by_target_angle(0, 0)
        axis_length = np.max(R) * 1.3

        self.ax.plot([0, axis_length], [0, 0], [0, 0], lw=1, c='red')
        self.ax.plot([0, 0], [0, axis_length], [0, 0], lw=1, c='green')
        self.ax.plot([0, 0], [0, 0], [0, axis_length], lw=1, c='blue')
        self.ax.set_xlim(-axis_length, axis_length)
        self.ax.set_ylim(-axis_length, axis_length)

        # X2, Y2 = np.meshgrid(xms, yns)
        # Z2 = np.zeros_like(X2)
        # ax.scatter(X2, Y2, Z2, marker='o', s=30)
        for n in range(self.N):
            for m in range(self.M):
                self.ax.text(self.xms[m], self.yns[n], 0, f"{self.M * n + m}", c='g', size=7, ha='center', va='center')
        self.angle_text = self.ax.text(self.xms[-1] + dx / 4, self.yns[0] + dy / 4, 0, "", ha='left', va='bottom')

        for receiver in receivers:
            receiver.init(self.ax)

        self.ani = FuncAnimation(fig, self.update, interval=100)
        return fig

    def update(self, _):
        if 0:
            R = self.get_pattern_data_by_target_angle(self.theta0_d, self.phi0_d)
        else:
            # phases = self.get_desired_phase(self.theta0_d, self.phi0_d)
            R = self.get_pattern_data_by_phased_array(self.phases)
            v = self.get_vector(self.phases)
            self.set_target_angle(v.theta, v.phi)

        xyz = spherical_to_cartesian(R, THETA, PHI)

        if hasattr(self, 'surf'):
            self.surf.remove()
        self.surf = self.ax.plot_surface(*xyz, cmap=plt.get_cmap('jet'),
                                         lw=0.1, alpha=0.3, rstride=1, cstride=1, aa=True)
        self.angle_text.set_text(f"θ: {self.theta0_d:7.0f}°\nφ: {self.phi0_d:7.0f}°")

        for receiver in receivers:
            receiver.update()


class Receiver():
    def __init__(self, name):
        self.name = name
        self.r, self.theta_d, self.phi_d = 0, 0, 0

    def init(self, ax):
        self.ax = ax
        self.scatter = ax.scatter([], [], [], marker='x', c='m', s=50)
        self.text = ax.text(0, 0, 0, "", c='m')
        self.line = ax.plot([], [], [], 'm--', lw=0.5)[0]

    def update(self):
        name = self.name if self.r else ""
        x, y, z = self.xyz
        self.scatter._offsets3d = ([x], [y], [z])
        self.text.remove()
        self.text = self.ax.text(x, y, z, name, c='m')
        self.line.set_data([0, x], [0, y])
        self.line.set_3d_properties([0, z])

    def set_spherical_coord(self, r, theta_d, phi_d):
        self.r, self.theta_d, self.phi_d = r, theta_d, phi_d

    def print_spherical_coord(self):
        print(f"{self.name} <- R: {self.r} / Theta: {self.theta_d} / Phi: {self.phi_d}")

    @property
    def xyz(self):
        return spherical_to_cartesian(self.r, np.deg2rad(self.theta_d), np.deg2rad(self.phi_d))


receivers = [Receiver(f"Rx#{i + 1}") for i in range(5)]


if __name__ == "__main__":
    esa = Esa(8, 8)
    fig = esa.plot()

    def on_press(event):
        if event.key == 'left':
            esa.theta0_d = max(esa.theta0_d - 5, -90)
        elif event.key == 'right':
            esa.theta0_d = min(esa.theta0_d + 5, 90)
        elif event.key == 'down':
            esa.phi0_d = max(esa.phi0_d - 5, -180)
        elif event.key == 'up':
            esa.phi0_d = min(esa.phi0_d + 5, 180)
    # fig.canvas.mpl_connect('key_press_event', on_press)

    plt.show()