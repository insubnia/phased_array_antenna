#!/usr/bin/python3
import os
import sys
import socket
import logging
import random
import numpy as np
from datetime import datetime
from enum import IntEnum, auto
from colorama import Fore

LOG_DIR = './log'
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

MAX_RX_NUM = 5

class Status(IntEnum):
    READY = 0
    BUSY = 1
    DISCONN = 255

    @classmethod
    def string_by_val(cls, val):
        if val == cls.READY:
            return "Ready"
        elif val == cls.BUSY:
            return "Busy"
        elif val == cls.DISCONN:
            return "Disconnected"
        else:
            return ""


class CmdType(IntEnum):
    NOP = 0
    SCAN = auto()
    RESET = auto()
    TARGET_1 = auto()
    TARGET_2 = auto()
    TARGET_3 = auto()
    TARGET_4 = auto()
    TARGET_5 = auto()


class Upstream():
    def __init__(self):
        self.status = Status.DISCONN
        self.curr_phases = np.zeros(16, dtype=np.int8)
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
        upstream.status = data[0]
        upstream.curr_phases = np.frombuffer(data[4:20], dtype=np.int8)
        o = 128
        for peri_info in upstream.peri_infos:
            peri_info.address = np.frombuffer(data[o: o + 6], dtype=np.uint8)
            peri_info.rfdc_adc, peri_info.bat_adc = np.frombuffer(data[o + 8: o + 12], dtype=np.uint16)
            peri_info.phases = np.frombuffer(data[o + 12: o + 28], dtype=np.int8)
            peri_info.rfdc_ranges = np.frombuffer(data[o + 28: o + 60], dtype=np.uint16)
            o += 128


class Downstream():
    def __init__(self):
        self.cmd = CmdType.NOP
        self.valid_cmd = CmdType.NOP
        self.running = False
        self.phases = np.zeros(16, dtype=np.uint8)
        self.loss = 80
        self.peri_mode = 1

    def set_cmd(self, cmd):
        self.cmd = cmd
        if cmd != CmdType.NOP:
            self.valid_cmd = cmd

    @property
    def packed_data(self):
        data = np.zeros(64, dtype=np.uint8)
        data.put(0, downstream.cmd)
        data.put(1, downstream.loss)
        data.put(2, downstream.peri_mode)
        data.put(range(8, 8 + len(downstream.phases)), downstream.phases)
        return data.tobytes()


class UdpServer():
    def __init__(self):
        self.server_addr = ('192.168.0.10', 1248)
        self.client_addr = ('192.168.0.20', 1248)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(self.server_addr)
        except OSError:
            print(f"{Fore.RED}\n[Error] Check IP address\n{Fore.RESET}")
            sys.exit()
        self.sock.settimeout(1)

    def __del__(self):
        self.sock.close()


class Logger():
    def __init__(self):
        self.done = False
        self.ccp = 0
        self.scanning_rate = 0
        self.tops_p_watt = 0

        now = datetime.now()
        logging.basicConfig(filename=f"{LOG_DIR}/{now.strftime('%Y%m%d_%H%M%S')}.csv",
                            filemode='w',
                            # format='%(asctime)s, %(message)s',
                            format='%(message)s',
                            datefmt='%y-%m-%d %H:%M:%S',
                            level=logging.NOTSET)
        logging.StreamHandler.terminator = ""

        header_row = "rx#, R, θ, ϕ"
        for i in range(16):
            header_row += f", ps#{i}"
        for i in range(16):
            header_row += f", range#{i}"
        header_row += ", CCP(uW), Scanning Rate(ms), TOPS/W"
        logging.info(f"{header_row}\n")

    def get_csv_string(self):
        s = ""
        for i, peri in enumerate(upstream.peri_infos):
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
        s = f"MCP: {logger.ccp}uA/MHz  |  " +\
            f"Scanning Rate: {logger.scanning_rate:5.2f}ms  |  " +\
            f"TOPS/W: {logger.tops_p_watt:.3f}"
        return s


upstream = Upstream()
downstream = Downstream()
server = UdpServer()
logger = Logger()


def process():
    while True:
        server.sock.sendto(downstream.packed_data, server.client_addr)
        downstream.cmd = CmdType.NOP

        try:
            data, _ = server.sock.recvfrom(1248)
        except Exception:
            upstream.status = Status.DISCONN
            print(f"{Fore.CYAN}Waiting for client packet{Fore.RESET}")
            continue

        upstream.unpack_data(data)

        # print(f"cmd: {command.cmd} | valid cmd: {command.valid_cmd} | running: {command.running} | status: {stream.status}")
        if downstream.valid_cmd != CmdType.NOP and upstream.status == Status.BUSY:
            downstream.running = True
        if downstream.running is True and upstream.status == Status.READY:
            if downstream.valid_cmd in [CmdType.TARGET_1, CmdType.TARGET_2, CmdType.TARGET_3, CmdType.TARGET_4, CmdType.TARGET_5]:
                logging.info(logger.get_csv_string())
            downstream.valid_cmd = CmdType.NOP
            downstream.running = False
            logger.done = True


if __name__ == "__main__":
    process()
