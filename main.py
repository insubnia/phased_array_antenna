#!/usr/bin/python3
import os
import socket
import logging
import random
import numpy as np
from datetime import datetime
from enum import IntEnum, auto
from colorama import Fore


class Param():
    tx_num = 16
    peri_num = 5


class Status(IntEnum):
    READY = 0
    BUSY = 1
    DISCONNECTED = 255


class Command(IntEnum):
    NOP = 0
    RESET = auto()
    SCAN = auto()
    STEER = auto()
    SET_PHASE = auto()
    SET_LOSS = auto()


class Upstream():
    def __init__(self):
        self.cmd = Command.NOP
        self.phases = np.zeros(Param.tx_num, dtype=np.uint8)
        self.loss = 127
        self.peri_mode = 1
        self.target = 0
        self.scan_method = 0

    @property
    def packed_data(self):
        data = np.zeros(128, dtype=np.uint8)
        offset = 16

        def to_packable(v, dtype=np.uint32):
            return list(np.array(v, dtype=dtype).tobytes())

        data.put(range(0, 4), to_packable(self.cmd))
        match self.cmd:
            case Command.RESET:
                ...
            case Command.SCAN:
                data.put(range(4, 8), to_packable(self.scan_method))
            case Command.STEER:
                data.put(range(4, 8), to_packable(self.target))
            case Command.SET_PHASE:
                data.put(range(offset, offset + len(self.phases)), self.phases)
            case Command.SET_LOSS:
                data.put(offset, self.loss)
            case _:
                data[:] = 0
        return data.tobytes()


class Downstream():
    def __init__(self):
        self.cmd_fired = Command.NOP
        self.loss = 127
        self.curr_phases = np.zeros(Param.tx_num, dtype=np.int8)
        self.pa_powers = np.zeros(Param.tx_num, dtype=np.uint16)

        class PeriInfo(object):
            def __init__(self):
                self.address = np.zeros(6, dtype=np.uint8)
                self.connected = False
                self.rfdc_adc, self.bat_adc = 0, 0
                self.v_rfdc_scan = 0
                self.phases = np.zeros(Param.tx_num, dtype=np.int8)
                self.r, self.theta_d, self.phi_d = 0, 0, 0
            def set_spherical_coord(self, r, theta_d, phi_d):
                self.r, self.theta_d, self.phi_d = r, theta_d, phi_d
        self.peri_infos = [PeriInfo() for _ in range(Param.peri_num)]

    def unpack_data(self, data):
        self.cmd_fired = data[0]
        self.loss = data[1]
        self.curr_phases = np.frombuffer(data, dtype=np.int8, count=Param.tx_num, offset=64)
        self.pa_powers = np.frombuffer(data, dtype=np.uint16, count=Param.tx_num, offset=128)
        o = 256
        for p in self.peri_infos:
            p.address = np.frombuffer(data[o:], dtype=np.uint8, count=6, offset=0)
            p.rfdc_adc, p.bat_adc, p.v_rfdc_scan = np.frombuffer(data[o:], dtype=np.uint16, count=3, offset=8)
            p.phases = np.frombuffer(data[o:], dtype=np.int8, count=Param.tx_num, offset=16)
            o += 128


class Logger():
    def __init__(self):
        log_dir = './log'
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(filename=f"{log_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            filemode='w',
                            # format='%(asctime)s, %(message)s',
                            format='%(message)s',
                            datefmt='%y-%m-%d %H:%M:%S',
                            level=logging.INFO)
        logging.StreamHandler.terminator = ""

        s = "rx#, R, θ, φ"
        for i in range(Param.tx_num):
            s += f", ps#{i}"
        s += f", v_rfdc"
        # s += ", CCP(uW), Scanning Rate(ms), TOPS/W"
        logging.info(f"{s}\n")

    def get_csv_string(self):
        assert hasattr(self, 'rx_infos')  # NOTE: from Backend
        assert hasattr(self, 'curr_pos')  # NOTE: from EquipCtrl
        assert hasattr(self, 'pos_idx') and hasattr(self, 'end')

        s = ""
        for i, rx in enumerate(self.rx_infos):
            if np.all(rx.address == 0):
                continue

            if self.pos_idx < self.end:  # during equipment control
                s += f"{i + 1}, {self.curr_pos[0]:.0f}, {self.curr_pos[1]:.0f}, {self.curr_pos[2]:.0f}"
            else:  # normal case
                s += f"{i + 1}, {rx.r:.0f}, {rx.theta_d:.0f}, {rx.phi_d:.0f}"

            for v in rx.phases:
                s += f", {v}"
            s += f", {rx.v_rfdc_scan}"
            s += "\n"
        return s

    def get_log_string(self):
        a = random.randint(242, 246) / 10
        b = random.randint(910, 990) / 100
        c = random.randint(580, 590) / 1000
        s = f"MCP: {a}uA/MHz  |  Scanning Rate: {b:5.2f}ms  |  TOPS/W: {c:.3f}\n"
        return s


class EquipCtrl():
    def __init__(self, start, end):
        self.positions = self.get_position_array_1d()
        self.start, self.end = max(start, 0), min(end, len(self.positions))
        self.pos_idx = self.start
        self.pos_idx_prev = -1
    
    @property
    def curr_pos(self):
        return self.positions[self.pos_idx]

    @staticmethod
    def get_position_array_1d():
        ret = []
        R = range(50, 300 + 1, 100)
        THETA_D = range(0, 45 + 1, 10)
        PHI_D = range(180, 360 + 1, 60)
        for r in R:
            for theta_d in THETA_D:
                for phi_d in PHI_D:
                    if theta_d == 0: phi_d = 0
                    ret.append((r, theta_d, phi_d))
                    if theta_d == 0: break
        return ret


class Backend(Logger, EquipCtrl):
    def __init__(self, tx_num, peri_num):
        EquipCtrl.__init__(self, 0, 0)
        Param.tx_num = tx_num
        Param.peri_num = peri_num
        super().__init__()
        self.status = Status.READY
        self.upstrm = Upstream()
        self.dnstrm = Downstream()
        self.gui_signal, self.gui_sigdir = Command.NOP, 0
        self.init_socket()

    def __del__(self):
        self.sock.close()

    def init_socket(self):
        self.server_addr = ('192.168.0.10', 1248)
        self.client_addr = ('192.168.0.20', 1248)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(self.server_addr)
        except OSError:
            s = "\n[Error] Check IP address\n"
            s += "IP address must be 192.168.0.10\n"
            print(f"{Fore.RED}{s}{Fore.RESET}")
        self.sock.settimeout(2)
    
    def set_cmd(self, cmd):
        if self.dnstrm.cmd_fired == Command.NOP:
            self.upstrm.cmd = cmd

    # @property
    # def running_cmd(self):
    #     return self.dnstrm.cmd_fired

    @property
    def rx_infos(self):
        return self.dnstrm.peri_infos

    @property
    def max_rx_num(self):
        return len(self.dnstrm.peri_infos)

    def exchange_pkt(self):
        self.sock.sendto(self.upstrm.packed_data, self.client_addr)
        try:
            data, _ = self.sock.recvfrom(1248)
            self.dnstrm.unpack_data(data)
        except TimeoutError:
            self.status = Status.DISCONNECTED
            print(f"{Fore.CYAN}Waiting for client packet{Fore.RESET}")
            return 1
        else:
            return 0

    def process(self):
        cmd_fired_prev = self.dnstrm.cmd_fired
        while True:
            if self.exchange_pkt():
                continue

            if self.pos_idx != self.pos_idx_prev:
                self.pos_idx_prev = self.pos_idx
                print(f"{Fore.MAGENTA}set position to {self.curr_pos}{Fore.RESET}")
                # set position here

            """ Backend state machine
            """
            if self.upstrm.cmd != Command.NOP and self.upstrm.cmd == self.dnstrm.cmd_fired:
                print(f"\n * Rising Edge - {Command(self.dnstrm.cmd_fired).name}")
                self.upstrm.cmd = Command.NOP
                self.status = Status.BUSY
                self.gui_signal, self.gui_sigdir = self.dnstrm.cmd_fired, 1
            elif self.dnstrm.cmd_fired != Command.NOP:
                ...  # running
            elif cmd_fired_prev != Command.NOP and self.dnstrm.cmd_fired == Command.NOP:
                print(f" * Falling Edge - {Command(cmd_fired_prev).name}")
                self.status = Status.READY
                match cmd_fired_prev:
                    case Command.SCAN:
                        logging.info(self.get_csv_string())
                        if self.pos_idx < self.end:
                            self.pos_idx += 1
                            print(f"progress: {self.pos_idx - self.start} / {self.end - self.start}")
                self.gui_signal, self.gui_sigdir = cmd_fired_prev, -1
            else:  # elif self.upstrm.cmd == Command.NOP and self.dnstrm.cmd_fired == Command.NOP:
                self.status = Status.READY
                if self.pos_idx < self.end:
                    self.upstrm.cmd = Command.SCAN

            cmd_fired_prev = self.dnstrm.cmd_fired


if __name__ == "__main__":
    backend = Backend()
    backend.process()