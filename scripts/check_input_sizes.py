#!/usr/bin/env python3
"""Build normal and BI/BTN variants; write measured capacity results. Never uploads."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release/inputtest/sizecheck"
CASES = [
    ("KNeoPiX S3 V1.5 IP", "inputbaseline_OKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15_IP", "release_OKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15_IP"),
    ("OpenKNXiao C6 Mini", "inputbaseline_OKNXHW_OPENKNXIAO_ESP32C6_MINI_V1", "release_OKNXHW_OPENKNXIAO_ESP32C6_MINI_V1"),
    ("UP1-GW-UART", "inputbaseline_OKNXHW_UP1_GW_UART", "release_OKNXHW_UP1_GW_UART"),
    ("QuinLED Dig-Quad V3 WiFi (4 MB)", "inputbaseline_QUINLED_DIG_QUAD_V3_WIFI", "release_QUINLED_DIG_QUAD_V3_WIFI"),
]


def run(command, name):
    print(f"Running {name} ...", flush=True)
    logfile = OUT / (name + ".log")
    with logfile.open("w") as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    return result.returncode, logfile.read_text(errors="replace")


def measure(pio, name, environment, kind):
    code, log = run([pio, "run", "-e", environment], kind + "-" + environment)
    result = {"board": name, "environment": environment, "kind": kind, "exit_code": code}
    for metric in ["RAM", "Flash"]:
        found = re.search(rf"{metric}:.*?used (\d+) bytes from (\d+) bytes", log)
        if found:
            used, limit = map(int, found.groups())
            result[metric.lower()] = {"used": used, "limit": limit, "free": limit - used}
    image = ROOT / ".pio/build" / environment / "firmware.bin"
    if code == 0 and image.exists():
        result["image_bytes"] = image.stat().st_size
        shutil.copy2(image, OUT / (kind + "-" + environment + ".bin"))
        # OGM-Common prunes old build directories; capture liveness while the ELF exists.
        packages = Path.home() / ".platformio/packages"
        tool = ("toolchain-riscv32-esp/bin/riscv32-esp-elf-nm" if "ESP32C6" in environment else
                "toolchain-rp2040-earlephilhower/bin/arm-none-eabi-nm" if "UP1" in environment else
                "toolchain-xtensa-esp-elf/bin/xtensa-esp32s3-elf-nm" if "KNEOPIX" in environment else
                "toolchain-xtensa-esp-elf/bin/xtensa-esp32-elf-nm")
        symbols = subprocess.check_output([str(packages / tool), "-C", "--defined-only", str(image.with_suffix(".elf"))], text=True)
        result["module_symbols"] = {module: module + "::setup()" in symbols
                                    for module in ["GpioBinaryInputModule", "VirtualButtonModule"]}
        if any(present != (kind == "inputs") for present in result["module_symbols"].values()):
            result["exit_code"] = 1
            result["errors"] = ["Input module liveness differs from the selected comparison mode"]
    if code != 0:
        result["errors"] = [line for line in log.splitlines() if "error:" in line.lower() or "Error:" in line or "***" in line][-12:]
    print(json.dumps(result), flush=True)
    return result


def summarize(results):
    for row in results:
        if "image_bytes" not in row or "flash" not in row:
            continue
        log = (OUT / (row["kind"] + "-" + row["environment"] + ".log")).read_text(errors="replace")
        # On RP, PlatformIO's nominal flash limit excludes FS but can include the
        # fixed KNX/OpenKNX regions. The real firmware boundary is the KNX offset.
        knx = re.search(r"\bKNX\s+0x([0-9a-fA-F]+)\s+-", log)
        capacity = int(knx.group(1), 16) if knx else row["flash"]["limit"]
        row["image_capacity"] = {"limit": capacity, "used": row["image_bytes"],
                                 "free": capacity - row["image_bytes"], "fits": row["image_bytes"] <= capacity}
    comparisons = []
    for name, normal, test in CASES:
        a, b = [next(r for r in results if r["environment"] == env) for env in [normal, test]]
        comparison = {"board": name, "normal_ok": a["exit_code"] == 0, "inputs_ok": b["exit_code"] == 0}
        if "flash" in a and "flash" in b:
            comparison["flash_increase"] = b["flash"]["used"] - a["flash"]["used"]
        if "image_bytes" in a and "image_bytes" in b:
            comparison.update(image_increase=b["image_bytes"] - a["image_bytes"],
                              image_free=b["image_capacity"]["free"], image_fits=b["image_capacity"]["fits"])
        comparisons.append(comparison)
    report = {"results": results, "comparisons": comparisons,
              "note": "Regular release environments include both modules; inputbaseline_* excludes them for comparison against the same Dev product. GPIO suitability and OTA staging require physical qualification. Image headroom uses actual application slots / RP KNX boundary, not nominal chip size."}
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(comparisons, indent=2), flush=True)
    return int(any(r["exit_code"] or not r.get("image_capacity", {}).get("fits", True) for r in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-only", action="store_true", help="Recheck existing logs/images without rebuilding")
    args = parser.parse_args()
    if args.report_only:
        return summarize(json.loads((OUT / "results.json").read_text())["results"])
    OUT.mkdir(parents=True, exist_ok=True)
    pio = shutil.which("pio") or str(Path.home() / ".platformio/penv/bin/pio")
    producer = shutil.which("OpenKNXproducer")
    if not producer:
        raise SystemExit("OpenKNXproducer is required")
    # Both baseline and regular builds use exactly the same normal Dev application.
    for command, name in [
        (["pwsh", "-NoProfile", "-File", "lib/OGM-HardwareConfig/generator/Build-HardwareProfile.ps1"], "normal-hardware"),
        (["python3", "scripts/inputtest.py", "prepare-shared"], "normal-input-wrappers"),
        (["python3", "scripts/inputtest.py", "bind"], "normal-input-bind"),
        ([producer, "create", "--Debug", "--HeaderFileName=include/knxprod.h",
          "--Output=release/inputtest/sizecheck/NeoPixel-normal.knxprod", "src/NeoPixel-Dev.xml"], "normal-product"),
    ]:
        code, _ = run(command, name)
        if code:
            raise SystemExit(f"{name} failed; see {OUT / (name + '.log')}")
    subprocess.run([sys.executable, "scripts/inputtest.py", "package", "--application", "NeoPixel-Dev"], cwd=ROOT, check=True)
    shutil.copy2(ROOT / "release/NeoPixel-Dev-xknx.knxprod", ROOT / "NeoPixel-Dev-xknx.knxprod")
    results = [measure(pio, name, normal, "normal") for name, normal, test in CASES]
    results += [measure(pio, name, test, "inputs") for name, normal, test in CASES]
    status = summarize(results)
    prototype = ROOT / ".pio/build" / CASES[0][2]
    for filename in ["firmware.bin", "firmware.factory.bin"]:
        if (prototype / filename).exists():
            shutil.copy2(prototype / filename, ROOT / "release/inputtest" / filename)
    return status


if __name__ == "__main__":
    sys.exit(main())
