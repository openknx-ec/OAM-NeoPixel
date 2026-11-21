"""Integration checks after Build-InputTest.ps1; no hardware or bus access."""
from pathlib import Path
import re
import csv
import hashlib
import json
import contextlib
import importlib.util
import io
import shutil
import subprocess
import unittest
from unittest.mock import patch
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = {"k": "http://knx.org/xml/project/20"}


def stored_parameters(root):
    result = {}
    params = root.find(".//k:Static/k:Parameters", NS)
    for node in params:
        memory = node.find("k:Memory", NS)
        if memory is None:
            continue
        if node.tag.endswith("}Union"):
            for p in node.findall("k:Parameter", NS):
                key = p.get("Id").split("_", 2)[2]
                result[key] = (int(memory.get("Offset")) + int(p.get("Offset", "0")), p.get("BitOffset", "0"))
        elif node.tag.endswith("}Parameter"):
            key = node.get("Id").split("_", 2)[2]
            result[key] = (int(memory.get("Offset")), memory.get("BitOffset", "0"))
    return result


class InputTestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ET.parse(ROOT / "src/NeoPixel-Dev.debug.xml").getroot()

    def test_existing_parameter_locations_preserved(self):
        # Dev 3.4 from origin/v1dev (157ee88), generated with the same dependencies.
        # Exclude only the appended BI/BTN parameters and their enable bits.
        current = stored_parameters(self.app)
        old = {key: value for key, value in current.items()
               if not key.split("-")[1].startswith(("24", "50"))
               and key not in {"UP-0099824", "UP-0099850"}}
        self.assertEqual(len(old), 69436)
        digest = hashlib.sha256(json.dumps(sorted(old.items()), separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, "7f2b249f5e6c9fb6f6e0d4999d27c3247c02dd51ed421b10ad44502e10c33882")

    def test_no_ko_collisions_and_prototype_ranges(self):
        objects = self.app.findall(".//k:ComObjectTable/k:ComObject", NS)
        numbers = [int(o.get("Number")) for o in objects]
        self.assertEqual(len(numbers), len(set(numbers)))
        self.assertEqual([n for n in numbers if 2000 <= n < 2010], [2000, 2001])
        self.assertEqual(sorted(n for n in numbers if n >= 2010), list(range(2010, 2058)))

    def test_gpio_and_virtual_channels_default_inactive(self):
        parameters = {p.get("Name"): p for p in self.app.findall(".//k:Static/k:Parameters//k:Parameter", NS)}
        for name in ["BI_Channel1Active", "BI_Channel2Active", *[f"BTN_b{i}Mode" for i in range(1, 5)]]:
            # Producer prefixes parameter names with the module's name.
            self.assertIn(name, parameters)
            self.assertEqual(parameters[name].get("Value"), "0")

    def test_inputs_grouped_under_function_blocks_with_independent_switches(self):
        dynamic = self.app.find(".//k:ApplicationProgram/k:Dynamic", NS)
        group = dynamic.find(".//k:Channel[@Number='FCB']", NS)
        self.assertIsNotNone(group)
        enabled = group.find("k:choose/k:when/k:ParameterBlock[@Name='FCB_FunctionBlockSettings']", NS)
        self.assertIsNotNone(enabled)
        with (ROOT / "test/hardware-input-audit.csv").open() as audit:
            visible_boards = {0} | {int(row["hardware_id"], 16) for row in csv.DictReader(audit) if row["gpio"]}
        hardware_gate = next(node for node in group.findall("k:choose", NS)
                             if node.get("ParamRefId").endswith("450000101"))
        hardware_when = hardware_gate.find("k:when", NS)
        self.assertEqual(set(map(int, hardware_when.get("test").split())), visible_boards)
        module_page = dynamic.find(".//k:ParameterBlock[@Name='BASE_OpenKNXproducerGeneratedModules']", NS)
        switch_gate = next(node for node in module_page.findall("k:choose", NS)
                           if node.get("ParamRefId") == hardware_gate.get("ParamRefId"))
        switch_when = switch_gate.find("k:when", NS)
        self.assertEqual(switch_when.get("test"), hardware_when.get("test"))
        for prefix, page, ref in [("BI", "BinaryInputs", "009982401"), ("BTN", "VirtualButtons", "009985001")]:
            self.assertIsNone(dynamic.find(f".//k:Channel[@Number='{prefix}']", NS))
            choose = next(node for node in hardware_when.findall("k:choose", NS) if node.get("ParamRefId").endswith(ref))
            block = choose.find(f"k:when[@test='1']/k:ParameterBlock[@Name='{page}']", NS)
            self.assertIsNotNone(block)
            self.assertEqual(block.get("ShowInComObjectTree"), "true")
            self.assertIsNotNone(block.find(f"k:ParameterBlock[@Name='{prefix}_Basic']", NS))
            self.assertIsNotNone(switch_when.find(f"k:ParameterRefRef[@RefId='{choose.get('ParamRefId')}']", NS))

    def test_packaged_product_identity_and_regex(self):
        products = [(ROOT / f"NeoPixel-{variant}-xknx.knxprod", number, version)
                    for variant, number, version in [("Dev", "AD01", "53"), ("Release", "AD00", "20")]]
        available = [(path, number, version) for path, number, version in products if path.exists()]
        self.assertTrue(available, "Generate a normal Dev or Release XKNX product first")
        for path, number, version in available:
            with ZipFile(path) as archive:
                name = next(n for n in archive.namelist() if f"_A-{number}-" in n and n.endswith(".xml"))
                app = ET.fromstring(archive.read(name))
                program = app.find(".//k:ApplicationProgram", NS)
                self.assertEqual(program.get("ApplicationVersion"), version)
                for node in app.iter():
                    if "Pattern" in node.attrib:
                        re.compile(node.get("Pattern"))

    def test_input_schema_mapping_compiles(self):
        flags = ["c++", "-std=c++11", "-x", "c++", "-fsyntax-only", "-",
                 "-Iinclude", "-Ilib/OGM-HardwareConfig/include", "-DARDUINO_ARCH_ESP32",
                 "-DOKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15", "-DKNX_IP_WIFI", "-DMASK_VERSION=0x57B0",
                 "-DNEOPIXEL_LOCAL_INPUT_TEST"]
        source = '''#include <cstdint>
#include "hardware.h"
#include "HardwareProfileData.h"
static_assert(OPENKNX_BI_GPIO_COUNT == 2, "two channels");
static_assert(hwInputGpio(0) == 41 && hwInputGpio(1) == 42, "board-defined raw pads");
static_assert(HW_INPUT_COUNT == 4 && hwInputGpio(4) == 255 && hwInputGpio(12) == 255 && hwInputGpio(255) == 255, "invalid connections stay disabled");
static_assert(HardwareProfile::inputSignalGpio(0x1322, 0) == 41, "own hardware");
static_assert(HardwareProfile::inputSignalGpio(0x1320, 0) == 255, "other hardware refused");
static_assert(!HardwareProfile::isReservedGpio(41), "inputs reserved only when active");
static_assert(hwPortGpio(0) == 2 && hwPortGpio(7) == 9, "output numbering unchanged");
'''
        result = subprocess.run(flags, input=source, text=True, cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_input_parameter_carriers_and_board_variants_share_only_their_byte(self):
        parameters = self.app.find(".//k:Static/k:Parameters", NS)
        for channel in (1, 2):
            candidates = []
            for union in parameters.findall("k:Union", NS):
                names = [p.get("Name") for p in union.findall("k:Parameter", NS)]
                if f"BI_Channel{channel}Port" in names:
                    candidates.append(union)
            self.assertEqual(len(candidates), 1)
            union = candidates[0]
            self.assertEqual(union.get("SizeInBit"), "8")
            for parameter in union.findall("k:Parameter", NS):
                self.assertEqual(parameter.get("Offset"), "0")
                self.assertEqual(parameter.get("BitOffset"), "0")
                self.assertEqual(parameter.get("Value"), "255")

    def test_all_audited_connections_match_the_generated_ets_table(self):
        script = "const fs=require('fs'),vm=require('vm');const c=vm.createContext({});vm.runInContext(fs.readFileSync('src/NeoPixel.hw.module.gen.js','utf8'),c);process.stdout.write(JSON.stringify(c.NEOHW_conflictBoards));"
        boards = json.loads(subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True))
        with (ROOT / "test/hardware-input-audit.csv").open() as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len({row["board"] for row in rows}), 40)
        self.assertEqual(len({row["environment"] for row in rows}), 44)
        for row in rows:
            ports = boards[str(int(row["hardware_id"], 16))]["inputs"]
            if row["gpio"]:
                self.assertEqual(ports[int(row["input_port"]) - 1], int(row["gpio"]), row)
            else:
                self.assertFalse(ports, row)

    def test_product_references_resolve_across_bi_and_neo_modules(self):
        ids = {n.get("Id") for n in self.app.iter() if n.get("Id")}
        for node in self.app.iter():
            for attribute in ("RefId", "ParamRefId"):
                reference = node.get(attribute, "")
                if "_R-" in reference:
                    self.assertIn(reference, ids, (node.tag, reference))

    def test_all_regular_environments_include_input_support(self):
        pio = shutil.which("pio") or str(Path.home() / ".platformio/penv/bin/pio")
        config = json.loads(subprocess.check_output([pio, "project", "config", "--json-output"], cwd=ROOT, text=True))
        for section, options in config:
            if not section.startswith("env:"):
                continue
            options = dict(options)
            ignored = set(options.get("lib_ignore", []))
            if section.startswith("env:inputbaseline_"):
                self.assertTrue({"OFM-BinaryInput", "OFM-VirtualButton"} <= ignored, section)
            else:
                self.assertFalse(ignored & {"OFM-BinaryInput", "OFM-VirtualButton"}, section)
                self.assertIn("NEOPIXEL_LOCAL_INPUTS", " ".join(options["build_flags"]), section)

    def test_size_report_uses_actual_rp_knx_boundary(self):
        spec = importlib.util.spec_from_file_location("input_sizes", ROOT / "scripts/check_input_sizes.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, "OUT", Path(tmp)), \
                patch.object(module, "CASES", [("RP", "normal", "inputs")]), contextlib.redirect_stdout(io.StringIO()):
            results = []
            for kind, size in [("normal", 900000), ("inputs", 920000)]:
                (Path(tmp) / f"{kind}-{kind}.log").write_text("KNX  0x0e0000 - 0x0f9000\n")
                results.append(dict(board="RP", environment=kind, kind=kind, exit_code=0,
                                    image_bytes=size, flash=dict(used=size, limit=1036288)))
            self.assertEqual(module.summarize(results), 1)
            self.assertEqual(results[1]["image_capacity"]["limit"], 917504)
            self.assertFalse(results[1]["image_capacity"]["fits"])


if __name__ == "__main__":
    unittest.main()
