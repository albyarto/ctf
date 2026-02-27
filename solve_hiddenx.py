#!/usr/bin/env python3
import argparse
import binascii
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

MASK32 = 0xFFFFFFFF


def u32(x: int) -> int:
    return x & MASK32


def rol32(x: int, r: int) -> int:
    x &= MASK32
    return ((x << r) | (x >> (32 - r))) & MASK32


def reverse_byte(b: int) -> int:
    return int(f"{b:08b}"[::-1], 2)


def run_z3_solve(printable: bool) -> bytes | None:
    vars_ = [f"c{i}" for i in range(36)]
    lines = ["(set-logic QF_BV)"]
    for v in vars_:
        lines.append(f"(declare-fun {v} () (_ BitVec 8))")
        if printable:
            lines.append(f"(assert (bvuge {v} #x20))")
            lines.append(f"(assert (bvule {v} #x7e))")

    a = "#xcc85f751"  # -863691923
    b = "#xbbc0ffee"  # -1144959338

    for i, v in enumerate(vars_):
        c32 = f"((_ zero_extend 24) {v})"
        t1 = f"(bvxor {a} (bvadd {c32} (_ bv{17*i} 32)))"
        a = f"(bvadd ((_ rotate_left 3) {t1}) #x9e3779b9)"
        t2 = f"(bvxor {a} (bvmul {c32} (_ bv93 32)))"
        b = f"(bvxor ((_ rotate_right 5) (bvadd {b} {t2})) #x7f4a7c95)"

    lines.append(f"(assert (= {a} #xc148be79))")  # -1052301703
    lines.append(f"(assert (= {b} #x0ec2bc66))")  # 247639510
    lines.append("(check-sat)")
    lines.append("(get-value (" + " ".join(vars_) + "))")

    smt = "\n".join(lines)
    with tempfile.NamedTemporaryFile("w", suffix=".smt2", delete=False) as f:
        f.write(smt)
        p = Path(f.name)

    try:
        proc = subprocess.run(["z3", str(p)], text=True, capture_output=True)
    finally:
        p.unlink(missing_ok=True)

    if proc.returncode != 0:
        raise RuntimeError(f"z3 failed: {proc.stderr.strip()}")

    out = proc.stdout
    if "unsat" in out:
        return None

    vals = re.findall(r"\(c(\d+) #x([0-9a-fA-F]{2})\)", out)
    if len(vals) != 36:
        raise RuntimeError(f"could not parse full model from z3 output:\n{out}")

    chars = [0] * 36
    for idx, hx in vals:
        chars[int(idx)] = int(hx, 16)
    return bytes(chars)


def derive_key(crc: int, key20: bytes, out_len: int = 32) -> bytes:
    st = u32(crc ^ 0xA5C3E2B7)
    out = bytearray(out_len)
    for i in range(out_len):
        ch = key20[i % len(key20)]
        st = u32(rol32(st ^ u32(ch + i * 51), 7) + 0x6D2B79F5)
        t = u32((st ^ (st >> 16)) + i * 158)
        out[i] = t & 0xFF
    return bytes(out)


def decrypt_payload(payload: bytes, key: bytes) -> bytes:
    st = 0xC0FFEE91
    out = bytearray(len(payload))
    for i, pb in enumerate(payload):
        v = reverse_byte(pb)
        st = u32(rol32(u32(st + key[i % len(key)] + i * 17), 3) ^ 0x9E3779B9)
        m = (st ^ (st >> 16)) & 0xFF
        out[i] = v ^ m
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-solve HiddenX.jar")
    ap.add_argument("--jar", default="HiddenX.jar")
    ap.add_argument("--output", default="output.zip")
    args = ap.parse_args()

    jar_path = Path(args.jar)
    if not jar_path.exists():
        print(f"[!] Missing {jar_path}")
        return 1

    if not shutil_which("z3"):
        print("[!] z3 binary not found.")
        print("    Install it with: sudo apt-get update && sudo apt-get install -y z3")
        return 1

    with zipfile.ZipFile(jar_path, "r") as zf:
        main_bytes = zf.read("ctf/hiddenx/Main.class")
        payload = zf.read("payload.bin")

    print("[*] Solving 36-byte checker with z3...")
    solved = run_z3_solve(printable=True)
    if solved is None:
        solved = run_z3_solve(printable=False)
    if solved is None:
        print("[!] Could not solve input")
        return 1

    solved_text = solved.decode("latin1")
    print(f"[+] Valid 36-byte input: {solved_text}")

    key20 = solved[3:23]
    crc = binascii.crc32(main_bytes) & 0xFFFFFFFF
    key = derive_key(crc, key20, 32)
    plain = decrypt_payload(payload, key)

    if not (len(plain) >= 4 and plain[0:2] == b"PK"):
        print("[!] Decryption failed integrity check")
        return 1

    out_zip = Path(args.output)
    out_zip.write_bytes(plain)
    print(f"[+] Wrote decrypted ZIP: {out_zip}")

    with zipfile.ZipFile(out_zip, "r") as zf:
        names = zf.namelist()
        print(f"[+] ZIP entries: {names}")
        flag_printed = False
        for name in names:
            data = zf.read(name)
            try:
                text = data.decode("utf-8", errors="ignore").strip()
            except Exception:
                continue
            if text:
                print(f"\n[+] {name}:\n{text}")
                flag_printed = True
                if "flag" in text.lower() or "ctf{" in text.lower():
                    break
        if not flag_printed:
            print("[!] No printable flag text found automatically. Check extracted files manually.")

    return 0


def shutil_which(name: str):
    from shutil import which
    return which(name)


if __name__ == "__main__":
    sys.exit(main())
