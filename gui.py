#!/opt/homebrew/bin/python3
import os
import sys
import threading
import numpy as np
from functools import partial
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from main import Status, Command, backend
from sim import Esa, receivers

loss = 127
ps_code_limit = 16

esa = Esa()
phases = np.zeros(esa.tx_num, dtype=np.int8)


def resource_path(relpath):
    if hasattr(sys, '_MEIPASS'):
        cwd = getattr(sys, '_MEIPASS')
    else:
        cwd = os.getcwd()
    return os.path.abspath(os.path.join(cwd, relpath))


def remap(x):  # will be deprecated
    return x
    table = (
        15, 14, 13, 12,
        11, 10, 9, 8,
        7, 6, 5, 4,
        3, 2, 1, 0,
    )
    return table[x]


def reshape_phases(_phases):
    sim_phases = np.ndarray((esa.N, esa.M), dtype=float)
    for n in range(esa.N):
        for m in range(esa.M):
            val = _phases[remap(esa.M * n + m)]
            sim_phases[n][m] = 0 if val == -1 else val * 22.5
    return sim_phases


def get_phase_display_string(arr1d=None, string=""):
    if arr1d is None:
        arr1d = phases
    for n in range(esa.N):
        string += "\n" if n > 0 else ""
        for m in range(esa.M):
            string += " " if m > 0 else ""
            code = arr1d[esa.M * n + m]
            string += f"{code:2d}"
    return string


def update_receivers():
    for i, receiver in enumerate(receivers):
        peri_info = backend.rx_infos[i]
        if peri_info.address[0] == 0:
            receiver.r = 0
            peri_info.theta_d = 0
            peri_info.phi_d = 0
            continue
        vector = Esa.get_vector(reshape_phases(peri_info.phases))
        receiver.set_spherical_coord(125, vector.theta, vector.phi)
        peri_info.theta_d = vector.theta
        peri_info.phi_d = vector.phi


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.widget = Widget()
        self.init_ui()

    def ss_by_status(self):
        ss_hash = {
            Status.READY: '''
                background-color: aliceblue;
            ''',
            Status.BUSY: '''
                background-color: aliceblue;
            ''',
            Status.DISCONNECTED: '''
                background-color: gray;
            ''',
        }
        return ss_hash[backend.status]

    @property
    def te(self):
        return self.widget.te

    def init_ui(self):
        self.setWindowTitle("WPT Visualizer")
        self.setMinimumWidth(1400)
        self.setCentralWidget(self.widget)
        QShortcut(QKeySequence('Ctrl+Q'), self, self.close)
        QShortcut(QKeySequence('Ctrl+W'), self, self.close)

        # for debug
        QShortcut(QKeySequence('p'), self, lambda : print(phases))

        self.statusbar = self.statusBar()

        streamer = threading.Thread(target=backend.process)
        streamer.daemon = True
        streamer.start()

        timer = QTimer(self)
        timer.timeout.connect(self.updater)
        timer.start(10)
        self.show()

    def updater(self):
        if backend.status == Status.READY:
            backend.upstrm.phases = phases.copy()
            self.widget.tx_group.setEnabled(True)
            self.widget.rx_group.setEnabled(True)
            self.widget.cmd_group.setEnabled(True)
        elif backend.status == Status.BUSY:
            phases.put(range(0, esa.tx_num), backend.dnstrm.curr_phases)
            self.widget.tx_group.setEnabled(False)
            self.widget.rx_group.setEnabled(True)
            self.widget.cmd_group.setEnabled(False)
        else:
            self.widget.tx_group.setEnabled(False)
            self.widget.rx_group.setEnabled(False)
            self.widget.cmd_group.setEnabled(False)
        self.statusbar.showMessage(Status(backend.status).name.lower())
        self.setStyleSheet(self.ss_by_status())

        """ Backend signal manager
        """
        if backend.gui_sigdir == 1:  # Rising Edge
            match backend.gui_signal:
                case Command.SCAN:
                    self.print("Scanning... ")
        elif backend.gui_sigdir == -1:  # Falling Edge
            match backend.gui_signal:
                case Command.RESET:
                    self.print("Reset whole phases\n")
                case Command.SCAN:
                    self.print("Done\n")
                case Command.STEER:
                    self.print(f"Steering to Rx#{backend.upstrm.target + 1}\n")
            update_receivers()
            fault_index = np.argwhere(backend.dnstrm.pa_powers < 295)
            if len(fault_index):
                self.print(f"No RF signal detected. Check PA: {fault_index.flatten()}\n")
            self.scroll_to_bottom()
            backend.gui_signal = Command.NOP
        backend.gui_sigdir = 0

    def print(self, *args, **kwargs):
        # self.widget.te.append(*args, **kwargs)
        self.te.insertPlainText(*args, **kwargs)

    def scroll_to_bottom(self):
        self.te.verticalScrollBar().setValue(self.te.verticalScrollBar().maximum())


class Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
                           background-color: ghostwhite;
                           """)
        self.init_ui()

    def init_ui(self):
        grid = QGridLayout()
        self.setLayout(grid)

        self.tx_group = self.create_tx_group()
        grid.addWidget(self.tx_group, 0, 1, 2, 1)
        self.rx_group = self.create_rx_group()
        grid.addWidget(self.rx_group, 1, 2)
        self.cmd_group = self.create_cmd_group()
        grid.addWidget(self.cmd_group, 0, 2)

        grid.addWidget(self.create_canvas(), 0, 0, 3, 1)
        grid.addWidget(self.create_console(), 2, 1, 1, 2)

    def style_groupbox(self, groupbox):
        groupbox_font = QFont()
        groupbox_font.setPointSize(15)
        groupbox_font.setBold(True)
        groupbox_ss = 'color: LightSlateGrey;'
        groupbox.setFont(groupbox_font)
        groupbox.setStyleSheet(groupbox_ss)

    def create_canvas(self):
        fig = esa.plot()
        canvas = FigureCanvas(fig)
        canvas.draw()
        return canvas

    def create_tx_group(self):
        groupbox = QGroupBox("Tx System")
        groupbox.setFixedSize(430, 675)
        self.style_groupbox(groupbox)

        grid = QGridLayout()
        groupbox.setLayout(grid)

        """ DSA
        """
        dsa_groupbox = QGroupBox("DSA")
        grid.addWidget(dsa_groupbox, 0, 0)
        dsa_groupbox.setFlat(True)

        hbox0 = QHBoxLayout()
        dsa_groupbox.setLayout(hbox0)
        dsa_label = QLabel()
        hbox0.addWidget(dsa_label)
        dsa_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dsa_label.setStyleSheet("font-size: 8pt;")
        dsa_slider = QSlider()
        hbox0.addWidget(dsa_slider)
        dsa_slider.setFixedHeight(75)
        dsa_slider.setRange(-127, 0)
        # dsa_slider.setInvertedAppearance(True)
        def dsa_changed():
            global loss
            val = dsa_slider.value()
            esa.set_amplitude(4 + 6 * (127 + val) / 127)
            dsa_label.setText(f"{val * 0.25:.2f} dB")
            backend.upstrm.loss = loss = -val
            backend.set_cmd(Command.SET_LOSS)
        dsa_slider.valueChanged.connect(dsa_changed)
        dsa_slider.setValue(-loss)
        QShortcut(QKeySequence('['), self, lambda: dsa_slider.setValue(dsa_slider.value() + 1))
        QShortcut(QKeySequence(']'), self, lambda: dsa_slider.setValue(dsa_slider.value() - 1))
        QShortcut(QKeySequence('{'), self, lambda: dsa_slider.setValue(dsa_slider.value() + 4))
        QShortcut(QKeySequence('}'), self, lambda: dsa_slider.setValue(dsa_slider.value() - 4))

        """ THETA
        """
        vbox1 = QVBoxLayout()
        # grid.addLayout(vbox1, 0, 1)
        theta_slider = QSlider(orientation=Qt.Orientation.Horizontal)
        vbox1.addWidget(theta_slider)
        theta_slider.setRange(-90, 90)
        theta_slider.setSingleStep(5)
        theta_label = QLabel()
        vbox1.addWidget(theta_label)
        theta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        theta_label.setMaximumHeight(15)
        theta_label.setText(f"θ: {theta_slider.value():3}°")
        theta_slider.valueChanged.connect(lambda: theta_label.setText(f"θ: {theta_slider.value():3}°"))

        """ PHI
        """
        vbox2 = QVBoxLayout()
        # grid.addLayout(vbox2, 0, 2)
        phi_slider = QSlider(orientation=Qt.Orientation.Horizontal)
        vbox2.addWidget(phi_slider)
        phi_slider.setRange(-180, 180)
        phi_slider.setSingleStep(10)
        phi_label = QLabel()
        vbox2.addWidget(phi_label)
        phi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        phi_label.setMaximumHeight(15)
        phi_label.setText(f"ϕ: {phi_slider.value():3}°")
        phi_slider.valueChanged.connect(lambda: phi_label.setText(f"ϕ: {phi_slider.value():3}°"))

        QShortcut(QKeySequence('h'), self, lambda: theta_slider.setValue(theta_slider.value() - 5))
        QShortcut(QKeySequence('l'), self, lambda: theta_slider.setValue(theta_slider.value() + 5))
        QShortcut(QKeySequence('j'), self, lambda: phi_slider.setValue(phi_slider.value() - 5))
        QShortcut(QKeySequence('k'), self, lambda: phi_slider.setValue(phi_slider.value() + 5))

        """ Global peripheral mode combobox
        """
        vbox3 = QVBoxLayout()
        grid.addLayout(vbox3, 0, 3)
        mode_label = QLabel("Peripheral mode")
        vbox3.addWidget(mode_label)
        mode_label.setFixedHeight(20)
        mode_combobox = QComboBox()
        vbox3.addWidget(mode_combobox)
        mode_combobox.setFixedHeight(25)
        mode_combobox.addItems(["Charging", "Scanning"])
        mode_combobox.setCurrentIndex(1)
        def combobox_changed():
            backend.upstrm.peri_mode = mode_combobox.currentIndex()
        mode_combobox.currentIndexChanged.connect(combobox_changed)
        vbox3.addWidget(QLabel())  # dummy for layout

        """ Phase dials
        """
        phase_dials = np.ndarray((esa.N, esa.M), dtype='O')
        phase_labels = np.ndarray((esa.N, esa.M), dtype='O')
        def create_single_phase_layout(n, m):
            idx = esa.M * n + m
            _groupbox = QGroupBox(f"Tx {idx}")
            _groupbox.setFlat(True)
            if esa.M > 4:
                _groupbox.setFixedSize(70, 90)
            else:
                _groupbox.setFixedSize(100, 140)

            grid = QGridLayout()
            _groupbox.setLayout(grid)

            label = phase_labels[n][m] = QLabel()
            grid.addWidget(label, 1, 0)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(13)

            dial = phase_dials[n][m] = QDial()
            grid.addWidget(dial, 0, 0)
            dial.setNotchesVisible(True)
            dial.setWrapping(True)
            dial.setRange(0, ps_code_limit)
            def dial_changed():
                if backend.gui_signal != Command.NOP:
                    return
                if dial.value() == ps_code_limit:
                    dial.setValue(0)
                phases.put(idx, dial.value())
                backend.set_cmd(Command.SET_PHASE)
            dial.valueChanged.connect(dial_changed)
            dial_changed()

            return _groupbox

        for n in range(esa.N):
            for m in range(esa.M):
                grid.addWidget(create_single_phase_layout(n, m), n + 1, m)

        def phase_updater():
            dsa_slider.setValue(-loss)
            for n in range(esa.N):
                for m in range(esa.M):
                    val = phases[esa.M * n + m]
                    phase_dials[n][m].setValue(val)
                    phase_labels[n][m].setText(f"{val:2}")
            esa.set_phases(reshape_phases(phases))
        timer = QTimer(self)
        timer.timeout.connect(phase_updater)
        timer.start(100)

        return groupbox

    def create_rx_group(self):
        groupbox = QGroupBox("Rx System")
        groupbox.setFixedSize(550, 450)
        self.style_groupbox(groupbox)

        grid = QGridLayout()
        groupbox.setLayout(grid)
        grid.setVerticalSpacing(15)

        rows = ["RF Level", "Battery\nLevel", "Phase\nProfile", "R(cm)\nθ(°)\nϕ(°)"]
        for i, desc in enumerate(rows):
            label = QLabel(desc)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight: bold")
            grid.addWidget(label, i + 1, 0)

        rx_widgets = []
        def create_rx_column(idx):
            _widgets = dict()
            rx_widgets.append(_widgets)

            """ Tag
            """
            label = QLabel(f"Rx #{idx}")
            grid.addWidget(label, 0, idx)
            _widgets['tag'] = label
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight: bold")
            label.setFixedHeight(20)

            """ RF-DC Status
            """
            rfdc_vbox = QVBoxLayout()
            grid.addLayout(rfdc_vbox, 1, idx)

            rfdc_img = QLabel("")
            rfdc_vbox.addWidget(rfdc_img)
            _widgets['rfdc_img'] = rfdc_img
            rfdc_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rfdc_img.setScaledContents(True)
            rfdc_img.setMaximumSize(120, 100)

            rfdc_label = QLabel("")
            rfdc_vbox.addWidget(rfdc_label)
            _widgets['rfdc_label'] = rfdc_label
            rfdc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rfdc_label.setStyleSheet("font-size: 8pt;")
            rfdc_label.setFixedSize(60, 10)

            """ Battery Status
            """
            bat_vbox = QVBoxLayout()
            grid.addLayout(bat_vbox, 2, idx)

            bat_pbar = QProgressBar()
            bat_vbox.addWidget(bat_pbar)
            _widgets['bat_pbar'] = bat_pbar
            bat_pbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bat_pbar.setMinimumSize(60, 10)
            bat_pbar.setTextVisible(True)

            bat_label = QLabel("")
            bat_vbox.addWidget(bat_label)
            _widgets['bat_label'] = bat_label
            bat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bat_label.setStyleSheet("font-size: 8pt;")
            bat_label.setFixedSize(60, 10)

            """ Phase Profile
            """
            profile_label = QLabel("")
            grid.addWidget(profile_label, 3, idx)
            _widgets['profile_label'] = profile_label
            profile_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if esa.M > 4:
                profile_label.setStyleSheet("font-size: 6pt;")

            """ Rx Positions
            """
            pos_grid = QGridLayout()
            grid.addLayout(pos_grid, 4, idx)
            r_le, theta_le, phi_le = QLineEdit(), QLineEdit(), QLineEdit()
            _widgets['vector'] = { 'r': r_le, 'theta': theta_le, 'phi': phi_le, }
            for i, le in enumerate([r_le, theta_le, phi_le]):
                le.setFixedWidth(50)
                # le.setValidator(QIntValidator())
                le.setReadOnly(True)
                pos_grid.addWidget(le, i, 1)

        for i in range(backend.max_rx_num):
            create_rx_column(i + 1)

        levels = (150, 300, 400, 700, 1000)
        pixmaps = [QPixmap(resource_path(f'deco/signal_{i}')) for i in range(len(levels) + 1)]
        def get_level(val):
            for i, upper in enumerate(levels):
                if val < upper:
                    return i
            return len(levels)

        def rx_updater():
            bat_adc_min, bat_adc_max = 2150, 3600
            for i, rx in enumerate(backend.rx_infos):
                w = rx_widgets[i]
                level = get_level(rx.rfdc_adc)
                bat_adc = min(bat_adc_max, max(bat_adc_min, rx.bat_adc))
                bat_pct = int((bat_adc - bat_adc_min) / (bat_adc_max - bat_adc_min) * 100)

                if backend.gui_signal == Command.SCAN:
                    w['tag'].setStyleSheet("background-color: yellow")
                elif (backend.upstrm.phases == rx.phases).all():
                    w['tag'].setStyleSheet("background-color: yellow")
                else:
                    w['tag'].setStyleSheet("background-color: ghostwhite")

                w['rfdc_img'].setPixmap(pixmaps[level])
                w['rfdc_label'].setText(f"{rx.rfdc_adc}")
                w['bat_pbar'].setValue(bat_pct)
                w['bat_label'].setText(f"{rx.bat_adc}")
                w['profile_label'].setText(get_phase_display_string(rx.phases))
                w['vector']['r'].setText("N/A")  # TODO: replace with RSSI
                w['vector']['theta'].setText(f"{rx.theta_d:.0f}")
                w['vector']['phi'].setText(f"{rx.phi_d:.0f}")

        timer = QTimer(self)
        timer.timeout.connect(rx_updater)
        timer.start(100)

        return groupbox

    def create_cmd_group(self):
        groupbox = QGroupBox("Commands")
        groupbox.setFixedSize(550, 160)
        self.style_groupbox(groupbox)

        vbox = QVBoxLayout()
        groupbox.setLayout(vbox)

        btn_ss = 'font-size: 11pt; font-style: italic;'

        # Action Buttons
        hbox0 = QHBoxLayout()
        vbox.addLayout(hbox0)
        scan_button1 = QPushButton("Steering Scan")
        hbox0.addWidget(scan_button1)
        scan_button1.setStyleSheet(btn_ss)
        scan_button1.setFixedHeight(50)
        def steering_scan():
            backend.upstrm.scan_method = 0
            backend.set_cmd(Command.SCAN)
        scan_button1.clicked.connect(steering_scan)
        scan_button1.setShortcut('s')

        scan_button2 = QPushButton("Full-sweep Scan")
        hbox0.addWidget(scan_button2)
        scan_button2.setStyleSheet(btn_ss)
        scan_button2.setFixedHeight(50)
        def fullsweep_scan():
            backend.upstrm.scan_method = 1
            backend.set_cmd(Command.SCAN)
        scan_button2.clicked.connect(fullsweep_scan)

        clear_button = QPushButton("Reset")
        hbox0.addWidget(clear_button)
        clear_button.setStyleSheet(btn_ss)
        clear_button.setFixedHeight(50)
        clear_button.clicked.connect(lambda: backend.set_cmd(Command.RESET))
        clear_button.setShortcut('0')

        hbox1 = QHBoxLayout()
        vbox.addLayout(hbox1)

        def target_button_clicked(i):
            backend.upstrm.target = i
            backend.set_cmd(Command.STEER)

        for i in range(backend.max_rx_num):
            button = QPushButton(f"Rx #{i + 1}")
            hbox1.addWidget(button)
            button.setStyleSheet(btn_ss)
            button.setFixedHeight(50)
            button.clicked.connect(partial(target_button_clicked, i))
            button.setShortcut(f'{i + 1}')

        return groupbox

    def create_console(self):
        groupbox = QGroupBox("Log")
        groupbox.setMinimumSize(500, 150)
        self.style_groupbox(groupbox)

        hbox0 = QVBoxLayout()
        groupbox.setLayout(hbox0)
        self.te = QTextEdit(readOnly=True)
        hbox0.addWidget(self.te)
        self.te.setFontPointSize(12)
        return groupbox


if __name__ == "__main__":
    appl = QApplication(sys.argv)
    appl.setWindowIcon(QIcon(resource_path('deco/satellite-antenna.png')))
    _ = Window()
    exit(appl.exec())