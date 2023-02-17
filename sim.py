#!/home/sis/.pyenv/shims/python3
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# constants
c = 3e11

# parameters
Fin = 5.8e9
Ampl = 8
M, N = 4, 4

# dependencies
weights = np.full((M, N), Ampl)
wave_length = c / Fin
k = 2 * np.pi / wave_length
dx = wave_length / 2
dy = wave_length / 2
xms = np.arange(0.5 - M / 2, M / 2, 1) * dx
yns = np.arange(0.5 - N / 2, N / 2, 1) * dy
yns = np.flip(yns)

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
THETA = np.arange(-90, 90 + 1, DEGREE_STEP)
PHI = np.arange(-180, 180 + 1, DEGREE_STEP)
THETA, PHI = np.deg2rad(np.meshgrid(THETA, PHI))

""" Global variables
"""
phases = np.zeros((M, N), dtype=float)
theta0, phi0 = 20, 30
surf = None


class Esa():
    M, N = 4, 4

    def __init__(self):
        self.theta0_d, self.phi0_d = 0, 0

    @staticmethod
    def set_target_angle(theta, phi):
        global theta0, phi0
        theta0, phi0 = theta, phi

    @staticmethod
    def set_phases(phases_d):
        global phases
        phases = phases_d

    @classmethod
    def set_amplitude(cls, ampl):
        cls.A = ampl
        weights.fill(cls.A)

    @staticmethod
    def get_vector(phases):
        pattern_data = Esa.get_pattern_data_by_phased_array(phases)
        idx = np.unravel_index(np.argmax(pattern_data, axis=None), pattern_data.shape)
        theta_d, phi_d = np.rad2deg(THETA[idx]), np.rad2deg(PHI[idx])
        return theta_d, phi_d

    @staticmethod
    def get_pattern_data_by_target_angle(theta_d, phi_d):
        theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)
        u0, v0 = u(theta_r, phi_r), v(theta_r, phi_r)
        r = np.zeros(np.shape(PHI))
        for n, yn in enumerate(yns):
            for m, xm in enumerate(xms):
                r = r + weights[m][n] * np.exp(1j * (
                    k * (xm * (u(THETA, PHI) - u0) + yn * (v(THETA, PHI) - v0))
                ))
        return abs(r)

    @staticmethod
    def get_pattern_data_by_phased_array(phase_d):
        phase = np.deg2rad(phase_d)
        r = np.zeros(np.shape(PHI))
        for n, yn in enumerate(yns):
            for m, xm in enumerate(xms):
                r = r + weights[m][n] * np.exp(1j * (
                    k * (xm * u(THETA, PHI) + yn * v(THETA, PHI)) +
                    phase[m][n]
                ))
        return abs(r)

    @staticmethod
    def get_desired_phase(theta_d, phi_d):
        theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)
        phase_d = np.ndarray((N, M))
        for m, xm in enumerate(xms):
            for n, yn in enumerate(yns):
                cmpx = np.exp(-1j * k * (xm * u(theta_r, phi_r) + yn * v(theta_r, phi_r)))
                phase_d[m][n] = np.angle(cmpx, deg=True)
        return phase_d


class Receiver():
    def __init__(self, name):
        self.name = name
        self.init_done = False
        self.r, self.theta_d, self.phi_d = 0, 0, 0

    def init_on_axis(self, ax):
        self.ax = ax
        self.scatter = ax.scatter([], [], [], marker='x', c='m', s=50)
        self.text = ax.text(0, 0, 0, "")
        self.line = ax.plot([], [], [], 'm--', lw=0.5)[0]
        self.init_done = True

    def update_plot(self):
        if self.init_done is False:
            return
        x, y, z = self.xyz
        name = self.name if self.r != 0 else ""

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


receivers = [Receiver(f"Rx#{i}") for i in range(1, 4)]


def update(frame):
    if 0:
        R = Esa.get_pattern_data_by_target_angle(theta0, phi0)
    else:
        # phases = Esa.get_desired_phase(theta0, phi0)
        R = Esa.get_pattern_data_by_phased_array(phases)
    X, Y, Z = spherical_to_cartesian(R, THETA, PHI)

    global surf
    if surf:
        surf.remove()
    surf = ax.plot_surface(X, Y, Z, cmap=plt.get_cmap('jet'),
                           alpha=0.3, linewidth=0.1, rstride=1, cstride=1, aa=True)
    # text.set_text(f"θ: {theta0}° \nϕ: {phi0}°")

    for receiver in receivers:
        receiver.update_plot()


def plot_sim():
    fig = plt.figure()
    fig.subplots_adjust(left=.03, right=.97)

    R = Esa.get_pattern_data_by_target_angle(0, 0)
    axis_length = np.max(R) * 1.3

    global ax
    ax = fig.add_subplot(projection='3d')
    ax.set_title("Beam Pattern", color='#778899', size=15, weight='bold', va='bottom')
    ax.view_init(elev=110, azim=-105, roll=-15)

    ax.plot([0, axis_length], [0, 0], [0, 0], lw=1, c='red')
    ax.plot([0, 0], [0, axis_length], [0, 0], lw=1, c='green')
    ax.plot([0, 0], [0, 0], [0, axis_length], lw=1, c='blue')
    ax.set_xlim(-axis_length, axis_length)
    ax.set_ylim(-axis_length, axis_length)

    # X2, Y2 = np.meshgrid(xms, yns)
    # Z2 = np.zeros_like(X2)
    # ax.scatter(X2, Y2, Z2, marker='o', s=30)
    for n in range(N):
        for m in range(M):
            ax.text(xms[m], yns[n], 0, f"{M * n + 3 - m}", c='g', size=7, ha='center', va='center')

    global text
    text = ax.text(xms[-1] + dx / 2, yns[-1] + dy / 2, 0, "")

    for receiver in receivers:
        receiver.init_on_axis(ax)

    global anim  # In order to extend life cycle since animation is activated when anim variable encounter plt.show
    anim = FuncAnimation(fig, update, interval=100)
    # anim.save('sim.gif', writer='imagemagick', fps=60)
    return fig


if __name__ == "__main__":
    fig = plot_sim()

    def on_press(event):
        global theta0, phi0
        if event.key == 'left':
            theta0 = max(theta0 - 5, -90)
        elif event.key == 'right':
            theta0 = min(theta0 + 5, 90)
        elif event.key == 'down':
            phi0 = max(phi0 - 5, -180)
        elif event.key == 'up':
            phi0 = min(phi0 + 5, 180)
    fig.canvas.mpl_connect('key_press_event', on_press)
    plt.show()

    """  Legacy code
    # Poly3DCollection | https://matplotlib.org/stable/api/_as_gen/mpl_toolkits.mplot3d.art3d.Poly3DCollection.html
    verts = np.dstack((X, Y, Z))
    surf.set_verts(verts)
    surf.set_3d_properties()
    """
