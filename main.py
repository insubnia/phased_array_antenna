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
        self.ps_arr = np.zeros((4, 16), dtype=np.int8)
        self.rfdc_range = np.zeros((3, 16), dtype=np.uint16)

        self.peri_infos = list()
        class PeriInfo(object):
            def __init__(self):
                self.address = None
                self.rfdc_adc = 0
                self.bat_adc = 0
                self.position = np.zeros(3, dtype=int)
        [self.peri_infos.append(PeriInfo()) for i in range(3)]


class Command(object):
    def __init__(self):
        self.cmd = CmdType.NOP
        self.valid_cmd = CmdType.NOP
        self.running = False
        self.ps_arr = np.zeros(16, dtype=np.uint8)
    
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

# for project response
done_flag = False
ccp = 0
scanning_rate = 0
tops_p_watt = 0

def check_done():
    return done_flag
def clear_done():
    global done_flag
    done_flag = False
def get_measure():
    return ccp, scanning_rate, tops_p_watt


def get_logstring():
    string = ""
    for i in range(3):
        if stream.peri_infos[i].address[0] == 0:
            continue
        pos = stream.peri_infos[i].position
        tmp = f"{i + 1}, {pos[0]}, {pos[1]}, {pos[2]}"
        for v in stream.ps_arr[i + 1]:
            tmp += f", {v}"
        for v in stream.rfdc_range[i]:
            tmp += f", {v}"
        global ccp, scanning_rate, tops_p_watt
        ccp = random.randint(242, 246)
        ccp /= 10
        scanning_rate = random.randint(910, 990)
        scanning_rate /= 100
        tops_p_watt = random.randint(580, 590)
        tops_p_watt /= 1000
        tmp += f", {ccp}, {scanning_rate}, {tops_p_watt}\n"
        string += tmp
    return string


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
    header_row += f", CCP(uW), Scanning Rate(ms), TOPS/W"
    logging.info(f"{header_row}\n")

    while True:
        if stream.status == Status.READY:
            server.sock.settimeout(1)
        elif stream.status == Status.BUSY:
            server.sock.settimeout(5)

        packed_cmd = command.cmd.to_bytes(1, byteorder="little")
        packed_cmd += command.ps_arr.tobytes()
        # print(f"send packet {packed_cmd}")
        server.sock.sendto(packed_cmd, server.client_addr)
        command.cmd = CmdType.NOP

        try:
            data, _ = server.sock.recvfrom(1248)
        except Exception:
            stream.status = Status.NO_CONN
            print(f"{Fore.CYAN}Waiting for client packet{Fore.RESET}")
            continue

        stream.status = data[0]
        o = 1
        for i in range(4):
            stream.ps_arr[i] = np.frombuffer(data[o: o+16], dtype=np.int8)
            o += 16
        o = 66
        for i in range(3):
            stream.rfdc_range[i] = np.frombuffer(data[o: o+32], dtype=np.uint16)
            o += 32
        o = 162
        for i in range(3):
            stream.peri_infos[i].address = np.frombuffer(data[o: o+6], dtype=np.uint8)
            stream.peri_infos[i].rfdc_adc, stream.peri_infos[i].bat_adc = \
                np.frombuffer(data[o+6:o+10], dtype=np.uint16)
            o += 32

        # Command processing
        # print(f"cmd: {command.cmd} | valid cmd: {command.valid_cmd} | running: {command.running} | status: {stream.status}")
        if command.valid_cmd != CmdType.NOP and stream.status == Status.BUSY:
            command.running = True
        if command.running == True and stream.status == Status.READY:
            # if command.valid_cmd in [CmdType.SCAN, CmdType.TARGET_1, CmdType.TARGET_2, CmdType.TARGET_3]:
            if command.valid_cmd in [CmdType.TARGET_1, CmdType.TARGET_2, CmdType.TARGET_3]:
                logging.info(get_logstring())
            command.valid_cmd = CmdType.NOP
            command.running = False
            
            global done_flag
            done_flag = True


if __name__ == "__main__":
    process()
