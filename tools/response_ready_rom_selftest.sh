#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import importlib.util
import sys
from pathlib import Path

repo = Path(sys.argv[1])


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


subrom = load("response_ready_subrom", repo / "src/l3_service/make_subrom.py")
search = load("response_ready_search", repo / "tools/search_error_response_candidate.py")


def assembled(fast=False):
    a = subrom.build_subrom(fast_no_disk_response_ready=fast)
    a.resolve()
    return a


control_rom, control_used = subrom.build()
fast_rom, fast_used = subrom.build(fast_no_disk_response_ready=True)
if (control_used, fast_used) != (2042, 2045):
    raise SystemExit(f"NG: generated code size is not 2042/2045: {control_used}/{fast_used}")
changed = tuple(i for i, pair in enumerate(zip(control_rom, fast_rom))
                if pair[0] != pair[1])
validated = search.validate_rom_intervention_bytes(
    bytes(control_rom), bytes(fast_rom), name="selftest")
if changed != validated:
    raise SystemExit("NG: ROM preflight did not return the actual offsets")
print(f"OK: control/fast ROM size=2042/2045 and {len(changed)}-byte diff")

inflated_default = (bytes(control_rom[:0x0100]) + b"\x00\x00\x00" +
                    bytes(control_rom[0x0100:-3]))
try:
    search.validate_default_rom_bytes(bytes(control_rom), inflated_default)
except search.SearchError:
    pass
else:
    raise SystemExit("NG: inflated-default preflight fault was not detected")
print("OK: inflated-default preflight fault detected")

try:
    search.validate_rom_intervention_bytes(
        bytes(control_rom), bytes(control_rom), name="identical-fault")
except search.SearchError:
    pass
else:
    raise SystemExit("NG: identical-ROM preflight fault was not detected")
print("OK: identical-ROM preflight fault detected")

# no_disk axis-1 is a one-byte request after a 256-byte response. The runtime
# result disproved PENDING; the only no-FDC one-byte table route is 0x06 tracked.
if (subrom.OBSERVED_SINGLE_RESPONSE_BY_REQUEST[1] != ((0x06,), 0x80)
        or 1 not in subrom.OBSERVED_SINGLE_TRACKED_ENTRIES):
    raise SystemExit("NG: 0x06 tracked table entry is invalid")
for a in (assembled(False), assembled(True)):
    pos = a.labels["_osbr_send_tracked"]
    target = a.code[pos + 1] | a.code[pos + 2] << 8
    if a.code[pos] != 0xCD or target != a.labels["SEND_BOOT_SINGLE_TRACKED"]:
        raise SystemExit("NG: tracked table route misses SEND_BOOT_SINGLE_TRACKED")
print("OK: target route is the 0x06 tracked table path, not PENDING")


def run_tracked_to_ready(a, count, *, fault_ready_to_default=False):
    """Execute the public Z80 instructions from tracked response to OUT $FD."""
    code = bytearray(a.code)
    if fault_ready_to_default:
        # Fast routine: LD A,B; JR C,normal; JP SEND_BYTE_READY.
        pos = a.labels["_boot_single_track_done"] + 3
        if code[pos] != 0xC3:
            raise SystemExit("NG: fast ready JP was not found")
        target = a.labels["SEND_BYTE"]
        code[pos + 1:pos + 3] = bytes((target & 0xff, target >> 8))
    pc = a.labels["SEND_BOOT_SINGLE_TRACKED"]
    ram = {subrom.BOOT_SINGLE_RESPONSE_COUNT: count,
           subrom.EXCHANGE3_REQUEST_ACTIVE: 0,
           subrom.RUN_LEN: 0}
    stack = []
    a_reg, b_reg, hl = 0x80, 0, 0
    z = carry = False
    tstates = 0
    io = []
    for _step in range(100):
        op = code[pc]
        if op == 0x47:  # LD B,A
            b_reg = a_reg; pc += 1; cost = 4
        elif op == 0x78:  # LD A,B
            a_reg = b_reg; pc += 1; cost = 4
        elif op == 0xF5:  # PUSH AF
            stack.append((a_reg, z, carry)); pc += 1; cost = 11
        elif op == 0xF1:  # POP AF
            a_reg, z, carry = stack.pop(); pc += 1; cost = 10
        elif op == 0x3A:  # LD A,(nn)
            addr = code[pc + 1] | code[pc + 2] << 8
            a_reg = ram.get(addr, 0); pc += 3; cost = 13
        elif op == 0x32:  # LD (nn),A
            addr = code[pc + 1] | code[pc + 2] << 8
            ram[addr] = a_reg; pc += 3; cost = 13
        elif op == 0x3C:  # INC A (carry preserved)
            a_reg = (a_reg + 1) & 0xff; z = a_reg == 0; pc += 1; cost = 4
        elif op == 0xFE:  # CP n
            value = code[pc + 1]
            z = a_reg == value; carry = a_reg < value; pc += 2; cost = 7
        elif op == 0x20:  # JR NZ,e
            delta = code[pc + 1] - 256 if code[pc + 1] >= 128 else code[pc + 1]
            taken = not z; pc = pc + 2 + delta if taken else pc + 2
            cost = 12 if taken else 7
        elif op == 0x28:  # JR Z,e
            delta = code[pc + 1] - 256 if code[pc + 1] >= 128 else code[pc + 1]
            taken = z; pc = pc + 2 + delta if taken else pc + 2
            cost = 12 if taken else 7
        elif op == 0x38:  # JR C,e
            delta = code[pc + 1] - 256 if code[pc + 1] >= 128 else code[pc + 1]
            taken = carry; pc = pc + 2 + delta if taken else pc + 2
            cost = 12 if taken else 7
        elif op == 0x37:  # SCF
            carry = True; pc += 1; cost = 4
        elif op == 0x21:  # LD HL,nn
            hl = code[pc + 1] | code[pc + 2] << 8; pc += 3; cost = 10
        elif op == 0x22:  # LD (nn),HL
            addr = code[pc + 1] | code[pc + 2] << 8
            ram[addr], ram[addr + 1] = hl & 0xff, hl >> 8
            pc += 3; cost = 16
        elif op == 0xAF:  # XOR A
            a_reg = 0; z = True; carry = False; pc += 1; cost = 4
        elif op == 0xC3:  # JP nn
            pc = code[pc + 1] | code[pc + 2] << 8; cost = 10
        elif op == 0xCD:  # CALL nn
            target = code[pc + 1] | code[pc + 2] << 8
            stack.append(pc + 3); pc = target; cost = 17
        elif op == 0xC9:  # RET
            pc = stack.pop(); cost = 10
        elif op == 0xDB:  # IN A,(n)
            port = code[pc + 1]; a_reg = 0x02 if port == 0xFE else 0
            io.append(("IN", port)); pc += 2; cost = 11
        elif op == 0xE6:  # AND n
            a_reg &= code[pc + 1]
            z = a_reg == 0; carry = False; pc += 2; cost = 7
        elif op == 0xD3:  # OUT (n),A
            port = code[pc + 1]; io.append(("OUT", port)); pc += 2; cost = 11
        else:
            raise SystemExit(f"NG: unsupported static opcode ${op:02X} at ${pc:04X}")
        tstates += cost
        if io[-1:] == [("OUT", 0xFD)]:
            return tstates, io, ram
    raise SystemExit("NG: static tracked path did not reach OUT $FD")


control = assembled(False)
fast = assembled(True)
control_t, control_io, _ = run_tracked_to_ready(control, 4)
fast_t, fast_io, _ = run_tracked_to_ready(fast, 4)
if (control_t, fast_t, control_t - fast_t) != (164, 85, 79):
    raise SystemExit(f"NG: tracked path is not 164T -> 85T: {control_t}/{fast_t}")
if control_io != [("IN", 0xFE), ("OUT", 0xFD)]:
    raise SystemExit(f"NG: default tracked I/O path is unexpected: {control_io}")
if fast_io != [("OUT", 0xFD)]:
    raise SystemExit(f"NG: fast tracked I/O path is unexpected: {fast_io}")
print("OK: tracked path removes one duplicate IN $FE (164T -> 85T)")

for startup_count in (0, 1, 2):
    _t, startup_io, ram = run_tracked_to_ready(fast, startup_count)
    if startup_io != control_io:
        raise SystemExit(f"NG: startup tracked response {startup_count} was shortened")
    if startup_count == 2 and ram[subrom.EXCHANGE3_REQUEST_ACTIVE] != 1:
        raise SystemExit("NG: third startup response did not arm exchange #3")
print("OK: first three startup tracked responses retain the default path/state")

fault_t, fault_io, _ = run_tracked_to_ready(
    fast, 4, fault_ready_to_default=True)
if fault_t == fast_t or fault_io != control_io:
    raise SystemExit("NG: SEND_BYTE_READY->SEND_BYTE fault was not detected")
print("OK: SEND_BYTE_READY->SEND_BYTE fault detected")

if search.READY_ROM_FAST_EXPECTED_SHIFT != -3:
    raise SystemExit("NG: requested ROM shift is not -3 clocks")
if search.validate_ready_rom_fast(-3, 5, 2, 2, True) != -3:
    raise SystemExit("NG: valid 5->2 clock result was rejected")
faults = ((-2, 5, 2, 2, True, 0), (-3, 5, 3, 2, True, 0),
          (-3, 5, 2, 3, True, 0), (-3, 5, 2, 2, False, 0),
          (-3, 5, 2, 2, True, 1))
for requested, control_clock, fast_clock, official_clock, artifact, fault in faults:
    try:
        search.validate_ready_rom_fast(
            requested, control_clock, fast_clock, official_clock, artifact,
            fault=fault)
    except search.SearchError:
        pass
    else:
        raise SystemExit("NG: measurement gate fault was not detected")
print("OK: requested/effective/official/artifact measurement faults detected")
PY
