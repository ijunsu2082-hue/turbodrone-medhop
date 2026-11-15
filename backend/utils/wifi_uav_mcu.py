"""Decode the MCU/control messages a WiFi-UAV drone sends alongside video."""
from __future__ import annotations

import re
from typing import Optional

# The stock app only uses the extended `66 14 ...` command on firmware this new.
EXTENDED_COMMAND_MIN_BUILD_DATE = 20211218


def parse_mcu_packet(packet: bytes) -> Optional[bytes]:
    """Return the message inside a `93 04` packet, or None for anything else."""
    if len(packet) < 12 or packet[0] != 0x93 or packet[1] != 0x04:
        return None
    if int.from_bytes(packet[2:4], "little") != len(packet):
        return None
    length = int.from_bytes(packet[8:10], "little")
    if length > len(packet) - 12:
        return None
    return packet[12:12 + length]


def _describe_version(raw: bytes) -> str:
    text = raw.decode("ascii", errors="replace").strip("\x00 ")
    notes = []
    if "NOFLOW" in text:
        notes.append("no-flow firmware")
    elif "FLOW" in text:
        notes.append("flow firmware")
    match = re.search(r"(?<!\d)(20\d{6})(?!\d)", text)
    if match:
        supported = int(match.group(1)) >= EXTENDED_COMMAND_MIN_BUILD_DATE
        notes.append(f"build {match.group(1)}, extended commands {'supported' if supported else 'NOT supported'}")
    suffix = f" ({'; '.join(notes)})" if notes else ""
    return f"firmware version: {text}{suffix}"


def describe_mcu_message(message: bytes) -> str:
    """Turn one MCU message into a human-readable log line."""
    if message[:2] == b"\x01\x65":
        return _describe_version(message[2:])
    if message[:2] == b"\x01\x67":
        return f"config: {message[2:].decode('ascii', errors='replace')}"
    if message[:2] == b"\x01\x69":
        return "MCU busy"
    if message[:2] == b"\x01\x6a":
        return "MCU disconnected"
    if len(message) >= 5 and message[:2] == b"\x88\x00" and message[-1] == 0x55:
        return (
            f"status: fly-state=0x{message[2]:02x} battery=0x{message[3]:02x} "
            f"flags=0x{message[4]:02x} raw={message.hex(' ')}"
        )
    return f"message: {message.hex(' ')}"
