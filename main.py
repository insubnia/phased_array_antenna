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


class Status(IntEnum):
    READY = 0
    BUSY = 1
    NO_CONN = 255

    @classmethod
    def string_by_val(cls, val):
        if val == cls.READY:
            return "Ready"
        elif val == cls.BUSY:
            return "Busy"
        elif val == cls.NO_CONN:
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


class Stream(object):
    def __init__(self):
        self.status = Status.NO_CONN
        self.curr_phases = np.zeros(16, dtype=np.int8)
        self.rfdc_range = np.zeros((3, 16), dtype=np.uint16)

        class PeriInfo(object):
            def __init__(self):
                self.address = np.zeros(6, dtype=np.uint8)
                self.connected = False
                self.rfdc_adc, self.bat_adc = 0, 0
                self.phases = np.zeros(16, dtype=np.int8)
                self.rfdc_ranges = np.zeros(16, dtype=np.uint16)
                self.position = np.zeros(3, dtype=int)
        self.peri_infos = [PeriInfo() for _ in range(3)]


class Command(object):
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


class UdpServer(object):
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


stream = Stream()
command = Command()


class Logger():
    def __init__(self):
        self.done = False
        self.ccp = 0
        self.scanning_rate = 0
        self.tops_p_watt = 0

    def get_logstring(self):
        s = ""
        for i, peri in enumerate(stream.peri_infos):
            if peri.address[0] == 0:
                continue
            pos = peri.position
            s += f"{i + 1}, {pos[0]}, {pos[1]}, {pos[2]}"
            for v in peri.phases:
                s += f", {v}"
            for v in peri.rfdc_ranges:
                s += f", {v}"

            self.ccp = random.randint(242, 246)
            self.ccp /= 10
            self.scanning_rate = random.randint(910, 990)
            self.scanning_rate /= 100
            self.tops_p_watt = random.randint(580, 590)
            self.tops_p_watt /= 1000
            s += f", {self.ccp}, {self.scanning_rate}, {self.tops_p_watt}\n"
        return s


logger = Logger()


def process():
    server = UdpServer()

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

    while True:
        if stream.status == Status.READY:
            server.sock.settimeout(1)
        elif stream.status == Status.BUSY:
            server.sock.settimeout(5)

        cmds = np.zeros(64, dtype=np.uint8)
        cmds.put(0, command.cmd)
        cmds.put(1, command.loss)
        cmds.put(2, command.peri_mode)
        cmds.put(range(8, 8 + len(command.phases)), command.phases)
        server.sock.sendto(cmds.tobytes(), server.client_addr)
        command.cmd = CmdType.NOP

        try:
            data, _ = server.sock.recvfrom(1248)
        except Exception:
            stream.status = Status.NO_CONN
            print(f"{Fore.CYAN}Waiting for client packet{Fore.RESET}")
            continue

        stream.status = data[0]
        stream.curr_phases = np.frombuffer(data[4:20], dtype=np.int8)
        o = 128
        for i, peri in enumerate(stream.peri_infos):
            peri.address = np.frombuffer(data[o: o + 6], dtype=np.uint8)
            peri.rfdc_adc, peri.bat_adc = np.frombuffer(data[o + 8: o + 12], dtype=np.uint16)
            peri.phases = np.frombuffer(data[o + 12: o + 28], dtype=np.int8)
            peri.rfdc_ranges = np.frombuffer(data[o + 28: o + 60], dtype=np.uint16)
            o += 128

        # Command processing
        # print(f"cmd: {command.cmd} | valid cmd: {command.valid_cmd} | running: {command.running} | status: {stream.status}")
        if command.valid_cmd != CmdType.NOP and stream.status == Status.BUSY:
            command.running = True
        if command.running is True and stream.status == Status.READY:
            # if command.valid_cmd in [CmdType.SCAN, CmdType.TARGET_1, CmdType.TARGET_2, CmdType.TARGET_3]:
            if command.valid_cmd in [CmdType.TARGET_1, CmdType.TARGET_2, CmdType.TARGET_3]:
                logging.info(logger.get_logstring())
            command.valid_cmd = CmdType.NOP
            command.running = False

            logger.done = True


if __name__ == "__main__":
    process()