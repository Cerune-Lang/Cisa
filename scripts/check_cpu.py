#!/usr/bin/env python3
"""Validate Cisa's CALL/RET behavior on Cerune's four execution routes."""
import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIRST = "encode_movi(0u8, 10u16),"
SECOND = "encode_movi(0u8, 20u16),"
ROUTES = (
    ("IR", ("run",)),
    ("MIR", ("run-mir",)),
    ("SSA", ("run-mir", "--ssa")),
    ("VM", ("run-vm",)),
)

@dataclass(frozen=True)
class Case:
    name: str
    expected: str
    replacements: tuple = ()

CASES = (
    Case("normal", "20\n10\n12\n"),
    Case("bad_call", "call target out of range\n",
         ((FIRST, "encode_call(17u16),"),)),
    Case("call_overflow", "stack overflow\n",
         ((FIRST, "encode_call(0u16),"),)),
    Case("empty_ret", "stack underflow\n",
         ((FIRST, "encode_ret(),"),)),
    Case("bad_ret", "return address out of range\n",
         ((FIRST, "encode_movi(0u8, 17u16),"),
          (SECOND, "encode_jmp(13u16),"))),
)

def build_case(original, case):
    # The fixtures depend on the 17-word demonstration ROM. Fail rather than
    # silently testing the original program if a future edit changes that ROM.
    if original.count("const ROM_SIZE: i64 = 17;") != 1:
        raise ValueError("expected the 17-instruction demonstration ROM")
    if original.count("program: [u32; ROM_SIZE] = [") != 1:
        raise ValueError("cannot locate the demonstration ROM")
    result = original
    for old, new in case.replacements:
        if result.count(old) != 1:
            raise ValueError(f"{case.name}: expected one occurrence of {old!r}")
        result = result.replace(old, new, 1)
    return result

def run_command(argv, timeout):
    try:
        return subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=timeout, check=False,
        ), None
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"{type(error).__name__}: {error}"

def check_case(binary, path, case, timeout):
    failures = 0
    result, error = run_command([str(binary), "check", str(path)], timeout)
    if error or result.returncode != 0 or result.stderr:
        print(f"FAIL {case.name} [check]: {error or result.stderr!r}", file=sys.stderr)
        return 1
    print(f"PASS {case.name} [check]")
    for route_name, route in ROUTES:
        # --ssa follows the source path in Cerune's CLI.
        command = [str(binary), route[0], str(path), *route[1:]]
        result, error = run_command(command, timeout)
        if error:
            print(f"FAIL {case.name} [{route_name}]: {error}", file=sys.stderr)
            failures += 1
            continue
        if (result.returncode == 0 and result.stdout == case.expected.encode("utf-8")
                and not result.stderr):
            print(f"PASS {case.name} [{route_name}]")
        else:
            failures += 1
            print(
                f"FAIL {case.name} [{route_name}]: "
                f"exit={result.returncode} stdout={result.stdout!r} "
                f"stderr={result.stderr[:500]!r} expected={case.expected!r}",
                file=sys.stderr,
            )
    return failures

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="cerune", help="Cerune binary or executable path")
    parser.add_argument("--source", type=Path, default=ROOT / "src" / "cpu.ceru")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 120:
        parser.error("timeout must be 1..120 seconds")
    binary = shutil.which(args.binary)
    if binary is None and Path(args.binary).is_file():
        binary = str(Path(args.binary).resolve())
    if binary is None:
        parser.error(f"Cerune executable not found: {args.binary}")
    try:
        original = args.source.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="cisa-call-ret-") as tmp:
            failures = 0
            for case in CASES:
                path = Path(tmp) / f"{case.name}.ceru"
                path.write_text(build_case(original, case), encoding="utf-8")
                failures += check_case(binary, path, case, args.timeout)
    except (OSError, ValueError) as error:
        print(f"FAIL Cisa regression setup: {error}", file=sys.stderr)
        return 1
    print(f"Cisa CALL/RET: {len(CASES)} cases x {len(ROUTES)} routes; failures: {failures}")
    return int(failures != 0)

if __name__ == "__main__":
    sys.exit(main())
