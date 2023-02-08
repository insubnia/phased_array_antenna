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
xms = np.flip(xms)
yns = np.flip(yns)

# Global Variables
phases = np.zeros((M, N), dtype=float)
theta0, phi0 = 20, 30
surf = None

# Essential functions
def u(_theta, _phi):
    return np.sin(_theta) * np.cos(_phi)
def v(_theta, _phi):
    return np.sin(_theta) * np.sin(_phi)

# Plot
DEGREE_STEP = 5
THETA = np.arange(-90, 90 + 1, DEGREE_STEP)
PHI = np.arange(-180, 180 + 1, DEGREE_STEP)
THETA, PHI = np.deg2rad(np.meshgrid(THETA, PHI))


rx_coords = np.zeros((3, 3), dtype=int)
class RxPlotObj():
    def __init__(self):
        self.scatter = None
        self.plot = None
        self.text = None
rx_plot_objs = [RxPlotObj() for _ in range(3)]

# rx_coords = np.array(((150, 45, 120), (150, 0, 0), (150, 45, 0)))


def get_pattern_data_from_target_angle(theta_d, phi_d):
    theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)

    r = np.zeros(np.shape(PHI))
    for m, xm in enumerate(xms):
        for n, yn in enumerate(yns):
            r = r + weights[m][n] * np.exp(1j * k * 1 * (
                (xm * (u(THETA, PHI) - u(theta_r, phi_r))) +
                (yn * (v(THETA, PHI) - v(theta_r, phi_r)))
            ))
    r = abs(r)
    return r


def get_pattern_data_from_phase(phase_d):
    phase = np.deg2rad(phase_d)
    r = np.zeros(np.shape(PHI))
    for m, xm in enumerate(xms):
        for n, yn in enumerate(yns):
            r = r + weights[m][n] * np.exp(1j * (
                (k * (xm * u(THETA, PHI) + yn * v(THETA, PHI))) +
                phase[m][n]
            ))
    r = abs(r)
    return r


def get_desired_phase(theta_d, phi_d):
    theta_r, phi_r = np.deg2rad(theta_d), np.deg2rad(phi_d)
    phase_d = np.ndarray((M, N))
    for m, xm in enumerate(xms):
        for n, yn in enumerate(yns):
            cmpx = np.exp(-1j * k * (xm * u(theta_r, phi_r) + yn * v(theta_r, phi_r)))
            phase_d[m][n] = np.angle(cmpx, deg=True)
    return phase_d


def spherical_to_cartesian(r, theta_r, phi_r):
    x = r * np.sin(theta_r) * np.cos(phi_r)
    y = r * np.sin(theta_r) * np.sin(phi_r)
    z = r * np.cos(theta_r)
    return x, y, z


def set_target_angle(theta, phi):
    global theta0, phi0
    theta0, phi0 = theta, phi

def set_phases(_phases_d):
    global phases
    phases = _phases_d

def set_rx_coord(idx, coord):
    rx_coords[idx] = coord


def plot_receivers():
    for i, coord in enumerate(rx_coords):
        obj = rx_plot_objs[i]

        # if all(coord == 0):
        if coord[0] < 5 or coord[0] > 300:
            obj.scatter._offsets3d = ([], [], [])
            obj.text.set_text("")
            obj.plot.set_data([], [])
            obj.plot.set_3d_properties([])
            continue

        r, theta, phi = coord[0], np.deg2rad(coord[1]), np.deg2rad(coord[2])
        x, y, z = spherical_to_cartesian(r, theta, phi)

        obj.scatter._offsets3d = ([x], [y], [z])
        obj.text.remove()
        obj.text = ax.text(x, y, z, f"Rx#{i}", c='m')
        obj.plot.set_data([0, x], [0, y])
        obj.plot.set_3d_properties([0, z])


def update(frame):
    if 0:
        R = get_pattern_data_from_target_angle(theta0, phi0)
    else:
        # phases = get_desired_phase(theta0, phi0)
        R = get_pattern_data_from_phase(phases)
    X, Y, Z = spherical_to_cartesian(R, THETA, PHI)

    global surf
    if surf:
        surf.remove()
    surf = ax.plot_surface(X, Y, Z, cmap=plt.get_cmap('jet'),
                           alpha=0.3, linewidth=0.1, rstride=1, cstride=1, antialiased=True)
    # text.set_text(f"θ: {theta0}° \nϕ: {phi0}°")

    plot_receivers()


def plot_sim():
    fig = plt.figure()
    fig.suptitle("Beam Pattern", color='slateblue', fontsize=10)

    R = get_pattern_data_from_target_angle(0, 0)
    axis_length = np.max(R) * 1.3

    global ax
    ax = fig.add_subplot(projection='3d')
    ax.view_init(elev=110, azim=-105, roll=-15)

    ax.plot([0, axis_length], [0, 0], [0, 0], linewidth=1, color='red')
    ax.plot([0, 0], [0, axis_length], [0, 0], linewidth=1, color='green')
    ax.plot([0, 0], [0, 0], [0, axis_length], linewidth=1, color='blue')
    ax.set_xlim(-axis_length, axis_length)
    ax.set_ylim(-axis_length, axis_length)

    # X2, Y2 = np.meshgrid(xms, yns)
    # Z2 = np.zeros_like(X2)
    # ax.scatter(X2, Y2, Z2, marker='o', s=30)
    for n in range(N):
        for m in range(M):
            ax.text(xms[m], yns[n], 0, f"{M * n + m + 1}", c='g', size=7, ha='center', va='center')

    global text
    text = ax.text(xms[-1] + dx / 2, yns[-1] + dy / 2, 0, "")

    # initialize rx plot objects
    for obj in rx_plot_objs:
        obj.scatter = ax.scatter([], [], [], marker='x', c='m', s=50)
        obj.text = ax.text(0, 0, 0, "")
        obj.plot = ax.plot([], [], [], 'm--', lw=0.5)[0]

    global anim  # In order to extend life cycle since animation is activated when anim_variable encounter plt.show
    anim = FuncAnimation(fig, update, interval=100)
    # anim.save('sim.gif', writer='imagemagick', fps=60)
    return fig


if __name__ == "__main__":
    fig = plot_sim()

    def on_press(event):
        global theta0, phi0
        if event.key == 'h':
            theta0 = max(theta0 - 5, -90)
        elif event.key == 'l':
            theta0 = min(theta0 + 5, 90)
        elif event.key == 'j':
            phi0 = max(phi0 - 5, -180)
        elif event.key == 'k':
            phi0 = min(phi0 + 5, 180)
    fig.canvas.mpl_connect('key_press_event', on_press)

    plt.show()

    """  Legacy code
    # Poly3DCollection | https://matplotlib.org/stable/api/_as_gen/mpl_toolkits.mplot3d.art3d.Poly3DCollection.html
    verts = np.dstack((X, Y, Z))
    surf.set_verts(verts)
    surf.set_3d_properties()

    img = plt.imread('aa.png')
    stepX, stepY = 20. / img.shape[0], 20. / img.shape[1]
    X1 = np.arange(-10, 10, stepX)
    Y1 = np.arange(-10, 10, stepY)
    X2, Y2 = np.meshgrid(X1, Y1)
    Z2 = np.zeros_like(X2)
    ax.plot_surface(X2, Y2, Z2, rstride=4, cstride=4, facecolors=img)
    """
