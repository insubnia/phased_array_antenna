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

from main import process, stream, command, Status, CmdType, logger
from sim import Esa, plot_sim, set_phases, set_target_angle, set_rx_coord

phases = np.zeros(16, dtype=np.int8)
loss = 80
esa = Esa()


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def remap(x):
    """
    table = (
        3, 2, 1, 0,
        7, 6, 5, 4,
        11, 10, 9, 8,
        15, 14, 13, 12,
    )
    """
    table = (
        12, 8, 4, 0,
        13, 9, 5, 1,
        14, 10, 6, 2,
        15, 11, 7, 3,
    )
    return table[x]


def get_phase_display_string(arr1d=None, string=""):
    if arr1d is None:
        arr1d = phases
    for r in range(esa.N):
        string += "\n" if r > 0 else ""
        for c in range(esa.M):
            string += " " if c > 0 else ""
            code = arr1d[remap(esa.M * r + c)]
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

        streamer = threading.Thread(target=process)
        streamer.daemon = True
        streamer.start()
        time.sleep(0.5)

        self.init_updater()
        self.show()

    def init_updater(self):
        statusbar = self.statusBar()
        statusbar.showMessage("Ready")

        def updater():
            command.loss = loss
            if stream.status == Status.READY:
                command.phases = phases.copy()  # copy stream data to gui data
                self.widget.tx_group.setEnabled(True)
                self.widget.rx_group.setEnabled(True)
                self.widget.cmd_group.setEnabled(True)
            elif stream.status == Status.BUSY:
                phases.put(range(0, 16), stream.curr_phases)  # reflect current phases of target
                self.widget.tx_group.setEnabled(False)
                self.widget.rx_group.setEnabled(True)
                self.widget.cmd_group.setEnabled(False)
            else:
                self.widget.tx_group.setEnabled(False)
                self.widget.rx_group.setEnabled(False)
                self.widget.cmd_group.setEnabled(False)
            statusbar.showMessage(Status.string_by_val(stream.status))

            for i, v in enumerate(stream.peri_infos):
                set_rx_coord(i, v.position)

            if logger.done:
                logger.done = False
                self.widget.te.append(f"MCP: {logger.ccp}uA/MHz  |  "
                                      f"Scanning Rate: {logger.scanning_rate:5.2f}ms  |  "
                                      f"TOPS/W: {logger.tops_p_watt:.3f}")

        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(50)


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
            loss = -val
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
            command.peri_mode = mode_combobox.currentIndex()
        mode_combobox.currentIndexChanged.connect(combobox_changed)
        vbox3.addWidget(QLabel())  # dummy for layout

        """ Phase dials
        """
        phase_dials = np.ndarray((esa.N, esa.M), dtype='O')
        def create_single_phase_layout(r, c):
            idx = remap(esa.M * r + c)
            _groupbox = QGroupBox(f"Tx {idx}")
            _groupbox.setFlat(True)
            _groupbox.setFixedSize(100, 140)

            grid = QGridLayout()
            _groupbox.setLayout(grid)

            label = QLabel()
            grid.addWidget(label, 1, 0)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(13)

            dial = phase_dials[r][c] = QDial()
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
            dial.valueChanged.connect(dial_changed)
            dial_changed()

            return _groupbox

        for r in range(esa.N):
            for c in range(esa.M):
                grid.addWidget(create_single_phase_layout(r, c), r + 1, c)

        def updater():
            # set_target_angle(theta_slider.value(), phi_slider.value())
            dsa_slider.setValue(-loss)
            sim_phases = np.ndarray((esa.N, esa.M), dtype=float)
            for r in range(esa.N):
                for c in range(esa.M):
                    val = phases[remap(esa.M * r + c)]
                    phase_dials[r][c].setValue(val)
                    sim_phases[r][c] = val * 22.5
            set_phases(sim_phases)
        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(100)

        return groupbox

    def create_rx_group(self):
        groupbox = QGroupBox("Rx System")
        groupbox.setFixedSize(430, 470)
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
            x_le, y_le, z_le = QLineEdit(), QLineEdit(), QLineEdit()
            for i, le in enumerate([x_le, y_le, z_le]):
                le.setFixedWidth(50)
                le.setValidator(QIntValidator())
                le.setText(str(stream.peri_infos[idx - 1].position[i]))
                pos_grid.addWidget(le, i, 1)
            x_le.returnPressed.connect(lambda: np.put(stream.peri_infos[idx - 1].position, 0, x_le.text()))
            y_le.returnPressed.connect(lambda: np.put(stream.peri_infos[idx - 1].position, 1, y_le.text()))
            z_le.returnPressed.connect(lambda: np.put(stream.peri_infos[idx - 1].position, 2, z_le.text()))

        for i in range(1, 4):
            create_rx_column(i)

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
            for i, peri in enumerate(stream.peri_infos):
                level = get_level(peri.rfdc_adc)
                rx_widgets[i]['rfdc_img'].setPixmap(pixmaps[level])
                rx_widgets[i]['rfdc_label'].setText(f"{peri.rfdc_adc}")
                bat_adc = min(bat_adc_max, max(bat_adc_min, peri.bat_adc))
                bat_pct = int((bat_adc - bat_adc_min) / (bat_adc_max - bat_adc_min) * 100)
                rx_widgets[i]['bat_pbar'].setValue(bat_pct)
                rx_widgets[i]['bat_label'].setText(f"{peri.bat_adc}")
                rx_widgets[i]['profile_label'].setText(get_phase_display_string(peri.phases))

        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(100)

        return groupbox

    def create_cmd_group(self):
        groupbox = QGroupBox("Commands")
        groupbox.setFixedSize(430, 160)
        self.style_groupbox(groupbox)

        vbox = QVBoxLayout()
        groupbox.setLayout(vbox)

        btn_ss = 'font-size: 11pt; font-style: italic;'

        # Action Buttons
        hbox0 = QHBoxLayout()
        vbox.addLayout(hbox0)
        scan_button = QPushButton("Scan")
        hbox0.addWidget(scan_button)
        scan_button.setStyleSheet(btn_ss)
        scan_button.setFixedHeight(50)
        scan_button.clicked.connect(lambda: command.set_cmd(CmdType.SCAN))
        clear_button = QPushButton("Reset")
        hbox0.addWidget(clear_button)
        clear_button.setStyleSheet(btn_ss)
        clear_button.setFixedHeight(50)
        clear_button.clicked.connect(lambda: (command.set_cmd(CmdType.RESET), phases.fill(0)))
        clear_button.setShortcut('0')

        hbox1 = QHBoxLayout()
        vbox.addLayout(hbox1)

        def target_button_clicked(i):
            command.set_cmd(CmdType.TARGET_1 + i)
            phases.put(range(0, 16), stream.peri_infos[i].phases)
            np.place(phases, phases < 0, 0)

        for i in range(3):
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