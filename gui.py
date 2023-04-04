#!/opt/homebrew/bin/python3
import os
import sys
import time
import threading
import numpy as np
from functools import partial
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from main import process, upstream, downstream, Status, Command, logger, MAX_RX_NUM
from sim import Esa, plot_sim, receivers

phases = np.zeros(16, dtype=np.int8)
loss = 127
esa = Esa()


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def remap(x):
    table = (
        0, 1, 2, 3,
        4, 5, 6, 7,
        8, 9, 10, 11,
        12, 13, 14, 15,
    )
    return table[x]


def reshape_phases(_phases):
    sim_phases = np.ndarray((esa.N, esa.M), dtype=float)
    for n in range(esa.N):
        for m in range(esa.M):
            val = _phases[remap(esa.M * n + m)]
            sim_phases[n][m] =  0 if val == -1 else val * 22.5
    return sim_phases


def get_phase_display_string(arr1d=None, string=""):
    if arr1d is None:
        arr1d = phases
    for n in range(esa.N):
        string += "\n" if n > 0 else ""
        for m in range(esa.M):
            string += " " if m > 0 else ""
            code = arr1d[remap(esa.M * n + m)]
            string += f"{code:2d}"
    return string


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.widget = Widget()
        self.setStyleSheet("""
                           background-color: aliceblue;
                           """)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("WPT Visualizer")
        self.setMinimumWidth(1400)
        self.setCentralWidget(self.widget)
        QShortcut(QKeySequence('Ctrl+Q'), self, self.close)
        QShortcut(QKeySequence('Ctrl+W'), self, self.close)

        self.statusbar = self.statusBar()
        self.statusbar.showMessage("Ready")

        streamer = threading.Thread(target=process)
        streamer.daemon = True
        streamer.start()

        time.sleep(0.5)

        timer = QTimer(self)
        timer.timeout.connect(self.updater)
        timer.start(10)
        self.show()

    def updater(self):
        if downstream.status == Status.READY:
            upstream.phases = phases.copy()
            self.widget.tx_group.setEnabled(True)
            self.widget.rx_group.setEnabled(True)
            self.widget.cmd_group.setEnabled(True)
        elif downstream.status == Status.BUSY:
            phases.put(range(0, 16), downstream.curr_phases)
            self.widget.tx_group.setEnabled(False)
            self.widget.rx_group.setEnabled(True)
            self.widget.cmd_group.setEnabled(False)
        else:
            self.widget.tx_group.setEnabled(False)
            self.widget.rx_group.setEnabled(False)
            self.widget.cmd_group.setEnabled(False)
        self.statusbar.showMessage(Status(downstream.status).name.lower())

        if logger.scan_done:
            logger.scan_done = False
            # self.widget.te.append(logger.get_log_string())
            for i, receiver in enumerate(receivers):
                peri_info = downstream.peri_infos[i]
                if peri_info.address[0] == 0:
                    receiver.r = 0
                    peri_info.theta_d = 0
                    peri_info.phi_d = 0
                    continue
                vector = Esa.get_vector(reshape_phases(peri_info.phases))
                receiver.set_spherical_coord(125, vector.theta, vector.phi)
                peri_info.theta_d = vector.theta
                peri_info.phi_d = vector.phi


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
        fig = plot_sim()
        canvas = FigureCanvas(fig)
        canvas.draw()
        return canvas

    def create_tx_group(self):
        groupbox = QGroupBox("Tx System")
        groupbox.setFixedSize(430, 720)
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
            upstream.loss = loss = -val
            upstream.cmd = Command.SET_LOSS
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
            upstream.peri_mode = mode_combobox.currentIndex()
        mode_combobox.currentIndexChanged.connect(combobox_changed)
        vbox3.addWidget(QLabel())  # dummy for layout

        """ Phase dials
        """
        phase_dials = np.ndarray((esa.N, esa.M), dtype='O')
        def create_single_phase_layout(n, m):
            idx = remap(esa.M * n + m)
            _groupbox = QGroupBox(f"Tx {idx}")
            _groupbox.setFlat(True)
            _groupbox.setFixedSize(100, 140)

            grid = QGridLayout()
            _groupbox.setLayout(grid)

            label = QLabel()
            grid.addWidget(label, 1, 0)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(13)

            dial = phase_dials[n][m] = QDial()
            grid.addWidget(dial, 0, 0)
            dial.setNotchesVisible(True)
            dial.setWrapping(True)
            dial.setRange(0, 16)
            def dial_changed():
                if dial.value() == 16:
                    dial.setValue(0)
                    return
                label.setText(f"{dial.value():2}")
                phases.put(idx, dial.value())
                upstream.cmd = Command.SET_PHASE
            # dial.valueChanged.connect(dial_changed)
            # dial_changed()

            return _groupbox

        for n in range(esa.N):
            for m in range(esa.M):
                grid.addWidget(create_single_phase_layout(n, m), n + 1, m)

        def updater():
            dsa_slider.setValue(-loss)
            for n in range(esa.N):
                for m in range(esa.M):
                    val = phases[remap(esa.M * n + m)]
                    phase_dials[n][m].setValue(val)
            Esa.set_phases(reshape_phases(phases))
        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(100)

        return groupbox

    def create_rx_group(self):
        groupbox = QGroupBox("Rx System")
        groupbox.setFixedSize(550, 470)
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
            """ Header
            """
            label = QLabel(f"Rx #{idx}")
            grid.addWidget(label, 0, idx)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight: bold")
            label.setFixedHeight(20)

            """ RF-DC Status
            """
            rfdc_vbox = QVBoxLayout()
            grid.addLayout(rfdc_vbox, 1, idx)

            _widgets = dict()
            rx_widgets.append(_widgets)

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

            """ Rx Positions
            """
            pos_grid = QGridLayout()
            grid.addLayout(pos_grid, 4, idx)
            r_le, theta_le, phi_le = QLineEdit(), QLineEdit(), QLineEdit()
            for i, le in enumerate([r_le, theta_le, phi_le]):
                le.setFixedWidth(50)
                le.setText("0")
                # le.setValidator(QIntValidator())
                le.setReadOnly(True)
                pos_grid.addWidget(le, i, 1)
            _widgets['vector'] = { 'r': r_le, 'theta': theta_le, 'phi': phi_le, }

        for i in range(MAX_RX_NUM):
            create_rx_column(i + 1)

        section_num = 6
        pixmaps = [QPixmap(resource_path(f'deco/signal_{i}')) for i in range(section_num)]
        def get_level(val):
            b = [0, 150, 500, 1200, 2000, 3000, 4096]  # len(b) must be section_num + 1
            for i in range(section_num):
                # print(f"[{i}/{section_num}] is {val} in range of {b[i]} ~ {b[i+1]}?")
                if b[i] <= val < b[i + 1]:
                    return i
            return section_num - 1

        def updater():
            bat_adc_min, bat_adc_max = 3000, 4095
            for i, peri in enumerate(downstream.peri_infos):
                w = rx_widgets[i]
                level = get_level(peri.rfdc_adc)
                bat_adc = min(bat_adc_max, max(bat_adc_min, peri.bat_adc))
                bat_pct = int((bat_adc - bat_adc_min) / (bat_adc_max - bat_adc_min) * 100)

                w['rfdc_img'].setPixmap(pixmaps[level])
                w['rfdc_label'].setText(f"{peri.rfdc_adc}")
                w['bat_pbar'].setValue(bat_pct)
                w['bat_label'].setText(f"{peri.bat_adc}")
                w['profile_label'].setText(get_phase_display_string(peri.phases))
                w['vector']['r'].setText(f"N/A")
                w['vector']['theta'].setText(f"{peri.theta_d:.0f}")
                w['vector']['phi'].setText(f"{peri.phi_d:.0f}")

        timer = QTimer(self)
        timer.timeout.connect(updater)
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
            upstream.scan_method = 0
            upstream.cmd = Command.SCAN
        scan_button1.clicked.connect(steering_scan)

        scan_button2 = QPushButton("Full-sweep Scan")
        hbox0.addWidget(scan_button2)
        scan_button2.setStyleSheet(btn_ss)
        scan_button2.setFixedHeight(50)
        def fullsweep_scan():
            upstream.scan_method = 1
            upstream.cmd = Command.SCAN
        scan_button2.clicked.connect(fullsweep_scan)

        clear_button = QPushButton("Reset")
        hbox0.addWidget(clear_button)
        clear_button.setStyleSheet(btn_ss)
        clear_button.setFixedHeight(50)
        clear_button.clicked.connect(lambda: (upstream.set_cmd(Command.RESET), phases.fill(0)))
        clear_button.setShortcut('0')

        hbox1 = QHBoxLayout()
        vbox.addLayout(hbox1)

        def target_button_clicked(i):
            upstream.target = i
            upstream.set_cmd(Command.STEER)
            phases.put(range(0, 16), downstream.peri_infos[i].phases)
            phases[phases < 0] = 0
            #np.place(phases, phases < 0, 0)

        for i in range(MAX_RX_NUM):
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
        return groupbox


if __name__ == "__main__":
    appl = QApplication(sys.argv)
    appl.setWindowIcon(QIcon(resource_path('deco/satellite-antenna.png')))
    _ = Window()
    exit(appl.exec())
