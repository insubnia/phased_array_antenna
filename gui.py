#!/opt/homebrew/bin/python3
import os
import sys
import time
import threading
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

from main import process, stream, command, Status, CmdType
from main import check_done, clear_done, get_measure

from sim import plot_sim, set_phases, set_target_angle, set_rx_coord


phase_shift = np.zeros(16, dtype=np.uint8)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def synchronizer():
    while True:
        if stream.status == Status.NO_CONN:
            pass
        # copy stream data to gui data
        command.ps_arr = phase_shift.copy()
        time.sleep(0.1)


def get_phase_display_string(arr=None, string=""):
    if arr is None:
        arr = phase_shift

    for r in reversed(range(4)):
        for c in reversed(range(4)):
            code = arr[4 * r + c]
            # string += f"{int(code * 5.6):3d}, "
            string += f"{code:2d}, "
        string += "\n"
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
        QShortcut(QKeySequence('Ctrl+Q'), self, self.close)
        QShortcut(QKeySequence('Ctrl+W'), self, self.close)

        self.setWindowTitle("Beamforming Control Center")
        self.setMinimumSize(1650, 900)
        self.setCentralWidget(self.widget)

        statusbar = self.statusBar()
        statusbar.showMessage("Ready")

        # self.setFixedSize(1050, 700)

        streamer = threading.Thread(target=process)
        streamer.daemon = True
        streamer.start()

        time.sleep(0.5)

        updater = threading.Thread(target=synchronizer)
        updater.daemon = True
        updater.start()

        def updater():
            for i, v in enumerate(stream.peri_infos):
                pos = v.position
                set_rx_coord(i, pos)

            if check_done():
                clear_done()
                ccp, scanning_rate, tops_p_watt = get_measure()
                self.widget.qe.append(f"MCP: {ccp}uA/MHz  |  Scanning Rate: {scanning_rate:5.2f}ms  |  TOPS/W: {tops_p_watt:.3f}")

            if stream.status == Status.READY:
                self.widget.set_mode(0)
            elif stream.status == Status.BUSY:
                self.widget.set_mode(1)
            else:
                self.widget.set_mode(2)
            statusbar.showMessage(Status.string_by_val(stream.status))

        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(100)

        self.show()


class Widget(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
                           background-color: ghostwhite;
                           """)
        self.groupbox_stylesheet = """
        color: LightSlateGrey;
        """
        self.groupbox_font = QFont()
        self.groupbox_font.setPointSize(15)
        self.groupbox_font.setBold(True)
        self.init_ui()

    def init_ui(self):
        grid = QGridLayout()

        self.phase_group = self.create_phase_group()
        grid.addWidget(self.phase_group, 0, 1, 3, 1)

        self.button_group = self.create_button_group()
        self.button_group.setFixedWidth(500)
        grid.addWidget(self.button_group, 0, 2)

        self.target_group = self.create_target_group()
        self.target_group.setFixedWidth(500)
        grid.addWidget(self.target_group, 1, 2)

        console = self.create_console()
        grid.addWidget(console, 2, 2)

        self.canvas = self.create_canvas()
        self.canvas.setFixedSize(600, 600)
        grid.addWidget(self.canvas, 0, 0, 3, 1)

        self.setLayout(grid)


    def create_canvas(self):
        fig = plot_sim()
        canvas = FigureCanvas(fig)
        canvas.draw()
        return canvas


    def set_mode(self, mode):
        if mode == 0:
            self.phase_group.setEnabled(True)
            self.button_group.setEnabled(True)
            self.target_group.setEnabled(True)
        elif mode == 1:
            self.phase_group.setEnabled(False)
            self.button_group.setEnabled(False)
            self.target_group.setEnabled(True)
        elif mode == 2:
            self.phase_group.setEnabled(False)
            self.button_group.setEnabled(False)
            self.target_group.setEnabled(False)

    def create_phase_group(self):
        groupbox = QGroupBox("Tx System Info.")
        groupbox.setStyleSheet(self.groupbox_stylesheet)
        groupbox.setFont(self.groupbox_font)
        groupbox.setMinimumSize(500, 300)

        grid = QGridLayout()

        vbox1 = QVBoxLayout()
        theta_label = QLabel()
        theta_slider = QSlider(orientation=Qt.Orientation.Horizontal)
        theta_slider.setRange(-90, 90)
        theta_slider.setSingleStep(5)
        theta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        theta_label.setMaximumHeight(30)
        theta_label.setText(f"θ: {theta_slider.value():3}°")
        theta_slider.valueChanged.connect(lambda : theta_label.setText(f"θ: {theta_slider.value():3}°"))
        vbox1.addWidget(theta_slider)
        vbox1.addWidget(theta_label)
        grid.addLayout(vbox1, 5, 0)

        vbox2 = QVBoxLayout()
        phi_slider = QSlider(orientation=Qt.Orientation.Horizontal)
        phi_slider.setRange(-180, 180)
        phi_slider.setSingleStep(10)
        phi_label = QLabel()
        phi_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        phi_label.setMaximumHeight(30)
        phi_label.setText(f"ϕ: {phi_slider.value():3}°")
        phi_slider.valueChanged.connect(lambda : phi_label.setText(f"ϕ: {phi_slider.value():3}°"))
        vbox2.addWidget(phi_slider)
        vbox2.addWidget(phi_label)
        grid.addLayout(vbox2, 5, 1)

        # FIXME: delete later
        # theta_slider.setValue(20)
        QShortcut(QKeySequence('h'), self, lambda : theta_slider.setValue(theta_slider.value() - 5))
        QShortcut(QKeySequence('l'), self, lambda : theta_slider.setValue(theta_slider.value() + 5))
        # phi_slider.setValue(30)
        QShortcut(QKeySequence('j'), self, lambda : phi_slider.setValue(phi_slider.value() - 5))
        QShortcut(QKeySequence('k'), self, lambda : phi_slider.setValue(phi_slider.value() + 5))

        _dials = []
        _labels = []
        def create_single_phase_layout(idx):
            groupbox = QGroupBox(f"Tx {idx}")
            groupbox.setFlat(True)

            grid = QGridLayout()

            dial = QDial()
            _dials.append(dial)
            # dial.setRange(0, 64)
            dial.setRange(0, 16)
            dial.setNotchesVisible(True)
            dial.setNotchTarget(8)
            dial.setWrapping(True)
            dial.valueChanged.connect(lambda: phase_shift.put(idx, dial.value()))
            grid.addWidget(dial, 0, 0)

            label = QLabel(f"{dial.value()}")
            _labels.append(label)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # label.setFixedSize(15, 10)
            grid.addWidget(label, 1, 0)

            groupbox.setLayout(grid)
            return groupbox

        for i in range(16):
            r, c = 4 - i // 4, 4 - i % 4 - 1
            grid.addWidget(create_single_phase_layout(i), r, c)

        def updater():
            # set_target_angle(theta_slider.value(), phi_slider.value())
            set_phases(np.flip(phase_shift).reshape(4, 4) * 22.5)
            for val, label, dial in zip(phase_shift, _labels, _dials):
                dial.setValue(val)
                # label.setText(f"{val * 5.6:.1f}")
                label.setText(f"{val:2}")
        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(100)

        groupbox.setLayout(grid)
        return groupbox

    def create_target_group(self):
        groupbox = QGroupBox("Rx System Info.")
        groupbox.setStyleSheet(self.groupbox_stylesheet)
        groupbox.setFont(self.groupbox_font)

        grid = QGridLayout()
        # grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(30)

        rows = ["RF Level", "Battery\nLevel", "Phase\nProfile(°)", "R(cm)\nθ(°)\nϕ(°)"]
        for i, desc in enumerate(rows):
            label = QLabel(desc)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight: bold")
            grid.addWidget(label, i+1, 0)
        for i in range(1, 4):
            label = QLabel(f"Target {i}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight: bold")
            label.setFixedHeight(20)
            grid.addWidget(label, 0, i)

        _rfdc_labels = []
        _rfdc_digits = []
        _vbat_pbars = []
        _vbat_labels = []
        _profile_labels = []
        def create_target_column(idx):
            # RF-DC
            vbox1 = QVBoxLayout()
            label1 = QLabel("")
            _rfdc_labels.append(label1)
            label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label1.setScaledContents(True)
            label1.setMaximumSize(120, 100)
            vbox1.addWidget(label1)

            label2 = QLabel("")
            _rfdc_digits.append(label2)
            label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label2.setStyleSheet("font-size: 8pt;")
            label2.setFixedSize(60, 10)
            vbox1.addWidget(label2)

            grid.addLayout(vbox1, 1, idx)

            # Battery
            vbox2 = QVBoxLayout()
            pbar = QProgressBar()
            _vbat_pbars.append(pbar)
            pbar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pbar.setFixedWidth(120)
            pbar.setTextVisible(True)
            vbox2.addWidget(pbar)

            label3 = QLabel("")
            _vbat_labels.append(label3)
            label3.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label3.setStyleSheet("font-size: 8pt;")
            label3.setFixedSize(60, 10)
            vbox2.addWidget(label3)

            grid.addLayout(vbox2, 2, idx)

            # Phase profile
            label3 = QLabel("")
            _profile_labels.append(label3)
            label3.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label3, 3, idx)

            pos_grid = QGridLayout()
            x_le, y_le, z_le = QLineEdit(), QLineEdit(), QLineEdit()
            for i, le in enumerate([x_le, y_le, z_le]):
                le.setFixedWidth(50)
                le.setValidator(QIntValidator())
                le.setText(str(stream.peri_infos[idx - 1].position[i]))
                pos_grid.addWidget(le, i, 1)
            x_le.textChanged.connect(lambda : np.put(stream.peri_infos[idx - 1].position, 0, x_le.text()))
            y_le.textChanged.connect(lambda : np.put(stream.peri_infos[idx - 1].position, 1, y_le.text()))
            z_le.textChanged.connect(lambda : np.put(stream.peri_infos[idx - 1].position, 2, z_le.text()))
            grid.addLayout(pos_grid, 4, idx)

        for i in range(1, 4):
            create_target_column(i)

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
            for i in range(3):
                level = get_level(stream.peri_infos[i].rfdc_adc)
                _rfdc_labels[i].setPixmap(pixmaps[level])
                _rfdc_digits[i].setText(f"{stream.peri_infos[i].rfdc_adc}")

                # 3000:4095 = 0:100
                min_level, max_level = 3000, 4095
                x = min(max_level, max(min_level, stream.peri_infos[i].bat_adc))
                vbat_percent = int((x - min_level) / (max_level - min_level) * 100)
                # print(f"{stream.peri_infos[i].bat_adc} -> {x} -> {vbat_percent}")
                _vbat_pbars[i].setValue(vbat_percent)
                _vbat_labels[i].setText(f"{stream.peri_infos[i].bat_adc}")

                _profile_labels[i].setText(get_phase_display_string(stream.ps_arr[i + 1]))

        timer = QTimer(self)
        timer.timeout.connect(updater)
        timer.start(100)

        groupbox.setLayout(grid)
        return groupbox

    def create_button_group(self):
        groupbox = QGroupBox("Commands")
        groupbox.setStyleSheet(self.groupbox_stylesheet)
        groupbox.setFont(self.groupbox_font)
        groupbox.setFixedSize(500, 200)
        groupbox.setFlat(True)

        def set_ps(idx):
            global phase_shift
            phase_shift = stream.ps_arr[idx].copy()

        grid = QGridLayout()

        button_stylesheet = """
        font-size: 11pt;
        font-style: italic;
        """

        # Action Buttons
        scan_button = QPushButton("Scan")
        scan_button.setStyleSheet(button_stylesheet)
        scan_button.setFixedHeight(60)
        scan_button.clicked.connect(lambda : command.set_cmd(CmdType.SCAN))
        grid.addWidget(scan_button, 0, 0, 1, 2)

        clear_button = QPushButton("Reset")
        clear_button.setStyleSheet(button_stylesheet)
        clear_button.setFixedHeight(60)
        clear_button.clicked.connect(lambda : (command.set_cmd(CmdType.RESET), phase_shift.fill(0)))
        grid.addWidget(clear_button, 0, 2, 1, 2)

        # Target Buttons
        label = QLabel("Beamforming toward ")
        label.setStyleSheet("""
                            font-size: 11pt;
                            font-weight: bold;
                            """)
        grid.addWidget(label, 1, 0)

        target1_button = QPushButton("Target 1")
        target1_button.setStyleSheet(button_stylesheet)
        target1_button.setFixedHeight(35)
        target1_button.clicked.connect(lambda : (command.set_cmd(CmdType.TARGET_1), set_ps(1)))
        grid.addWidget(target1_button, 1, 1)

        target2_button = QPushButton("Target 2")
        target2_button.setStyleSheet(button_stylesheet)
        target2_button.font
        target2_button.setFixedHeight(35)
        target2_button.clicked.connect(lambda : (command.set_cmd(CmdType.TARGET_2), set_ps(2)))
        grid.addWidget(target2_button, 1, 2)

        target3_button = QPushButton("Target 3")
        target3_button.setStyleSheet(button_stylesheet)
        target3_button.setFixedHeight(35)
        target3_button.clicked.connect(lambda : (command.set_cmd(CmdType.TARGET_3), set_ps(3)))
        grid.addWidget(target3_button, 1, 3)

        groupbox.setLayout(grid)
        return groupbox

    def create_console(self):
        groupbox = QGroupBox("Log")
        groupbox.setStyleSheet(self.groupbox_stylesheet)
        groupbox.setFont(self.groupbox_font)
        groupbox.setMinimumSize(500, 150)

        layout = QVBoxLayout()
        self.qe = QTextEdit(readOnly=True)
        layout.addWidget(self.qe)
        groupbox.setLayout(layout)
        return groupbox


if __name__ == "__main__":
    appl = QApplication(sys.argv)
    appl.setWindowIcon(QIcon(resource_path('deco/satellite-antenna.png')))
    _ = Window()
    exit(appl.exec())
