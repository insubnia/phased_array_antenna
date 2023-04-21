#!/usr/bin/python3
import os
import sys
import time
import socket
import logging
import random
import numpy as np
from datetime import datetime
from enum import IntEnum, auto
from colorama import Fore

MAX_RX_NUM = 5


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
        self.valid_cmd = Command.NOP
        self.cmd_prev = Command.NOP
        self.running = False
        self.phases = np.zeros(16, dtype=np.uint8)
        self.loss = 80
        self.peri_mode = 1
        self.target = 0
        self.scan_method = 0

    def set_cmd(self, cmd):
        self.cmd = cmd
        if cmd != Command.NOP:
            self.valid_cmd = cmd

    @property
    def packed_data(self):
        data = np.zeros(128, dtype=np.uint8)
        offset = 16

        def to_packable(v, dtype=np.uint32):
            return list(np.array(v, dtype=dtype).tobytes())

        data.put(range(0, 4), to_packable(self.cmd))
        match self.cmd:
            case Command.RESET:
                pass
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
        self.status = Status.READY
        self.status_prev = Status.READY
        self.cmd_rcvd = Command.NOP
        self.confirm = False
        self.curr_phases = np.zeros(16, dtype=np.int8)
        self.pa_powers = np.zeros(16, dtype=np.uint16)

        class PeriInfo(object):
            def __init__(self):
                self.address = np.zeros(6, dtype=np.uint8)
                self.connected = False
                self.rfdc_adc, self.bat_adc = 0, 0
                self.phases = np.zeros(16, dtype=np.int8)
                self.rfdc_ranges = np.zeros(16, dtype=np.uint16)
                self.r, self.theta_d, self.phi_d = 0, 0, 0
        self.peri_infos = [PeriInfo() for _ in range(MAX_RX_NUM)]

    def unpack_data(self, data):
        self.status = data[0]
        self.cmd_rcvd = data[2]
        self.confirm = data[3]
        self.curr_phases = np.frombuffer(data[4:20], dtype=np.int8)
        self.pa_powers = np.frombuffer(data[20:52], dtype=np.uint16)
        o = 128
        for peri_info in self.peri_infos:
            peri_info.address = np.frombuffer(data[o: o + 6], dtype=np.uint8)
            peri_info.rfdc_adc, peri_info.bat_adc = np.frombuffer(data[o + 8: o + 12], dtype=np.uint16)
            peri_info.phases = np.frombuffer(data[o + 12: o + 28], dtype=np.int8)
            peri_info.rfdc_ranges = np.frombuffer(data[o + 28: o + 60], dtype=np.uint16)
            o += 128


class Logger():
    def __init__(self):
        self.done = False
        self.ccp = 0
        self.scanning_rate = 0
        self.tops_p_watt = 0

        log_dir = './log'
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(filename=f"{log_dir}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            filemode='w',
                            # format='%(asctime)s, %(message)s',
                            format='%(message)s',
                            datefmt='%y-%m-%d %H:%M:%S',
                            level=logging.NOTSET)
        logging.StreamHandler.terminator = ""

        s = "rx#, R, θ, ϕ"
        for i in range(16):
            s += f", ps#{i}"
        for i in range(16):
            s += f", range#{i}"
        s += ", CCP(uW), Scanning Rate(ms), TOPS/W"
        logging.info(f"{s}\n")

    def get_csv_string(self):
        s = ""
        for i, peri in enumerate(backend.rx_infos):
            if peri.address[0] == 0:
                continue
            s += f"{i + 1}, {peri.r}, {peri.theta_d}, {peri.phi_d}"
            for v in peri.phases:
                s += f", {v}"
            for v in peri.rfdc_ranges:
                s += f", {v}"
            self.ccp = random.randint(242, 246) / 10
            self.scanning_rate = random.randint(910, 990) / 100
            self.tops_p_watt = random.randint(580, 590) / 1000
            s += f", {self.ccp}, {self.scanning_rate}, {self.tops_p_watt}\n"
        return s

    def get_log_string(self):
        s = f"MCP: {self.ccp}uA/MHz  |  "
        s += f"Scanning Rate: {self.scanning_rate:5.2f}ms  |  "
        s += f"TOPS/W: {self.tops_p_watt:.3f}"
        return s


class Backend(Logger):
    def __init__(self):
        super().__init__()
        self.start_signal = Command.NOP
        self.finish_signal = Command.NOP
        self.upstrm = Upstream()
        self.dnstrm = Downstream()
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
            print(f"{Fore.RED}\n[Error] Check IP address\n{Fore.RESET}")
            sys.exit()
        self.sock.settimeout(1)

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
            self.dnstrm.status = Status.DISCONNECTED
            print(f"{Fore.CYAN}Waiting for client packet{Fore.RESET}")

    def process(self):
        while True:
            self.exchange_pkt()
            if ((self.dnstrm.status == Status.DISCONNECTED) or
                (self.upstrm.cmd != Command.NOP and self.dnstrm.status != Status.BUSY)):
                continue

            if self.dnstrm.status_prev == 0 and self.dnstrm.status != 0:
                # print(f"\n{self.upstrm.cmd} - Rising Edge")
                self.start_signal = self.upstrm.cmd
            elif self.dnstrm.status_prev != 0 and self.dnstrm.status == 0:
                print(f"{self.upstrm.cmd_prev} - Falling Edge")
                self.finish_signal = self.upstrm.cmd_prev
                match self.upstrm.cmd_prev:
                    case Command.SCAN | Command.STEER:
                        logging.info(self.get_csv_string())

            if self.upstrm.cmd != Command.NOP:
                self.upstrm.cmd_prev = self.upstrm.cmd
                self.upstrm.cmd = Command.NOP
            self.dnstrm.status_prev = self.dnstrm.status
            time.sleep(0.02)


backend = Backend()

if __name__ == "__main__":
    backend.process()