#!/usr/bin/env python3
"""Compile each release environment's board input metadata and write a connector audit."""
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def notes(board):
    if 'MINI' in board or 'KNEOPIX' in board:
        mcu = next(m for m in ['ESP32S3', 'RP2350', 'RP2040', 'ESP32C3', 'ESP32C5', 'ESP32C6'] if m in board)
        raw = {'ESP32S3': 'Raw D12/41, D11/42 and JTAG 40/39.',
               'RP2350': 'Raw back pads D11-D18: GPIO21/20/17/16/11/12/10/9.',
               'ESP32C5': 'Raw JTAG pads: GPIO5/3/4/2.',
               'ESP32C6': 'Raw JTAG pads: GPIO7/5/6/4.',
               'RP2040': 'No additional free back GPIOs declared.',
               'ESP32C3': 'No additional free back GPIOs declared.'}[mcu]
        if 'MINI' in board:
            access, text = 'terminal + module pad', 'Eight direct 3.3 V terminals D1-D5/D8-D10; share GPIOs with outputs.'
        elif board.endswith('_V1'):
            access, text = 'terminal + module pad', 'V1 TXS0108E terminals are bidirectional with internal pullups: dry contact to GND, LED disconnected.'
        else:
            access, text = 'raw module pad only', 'V1.5 LED terminals are output-only. Input access is exclusively on raw MCU-module pads, including D1-D5/D8-D10 that share GPIOs with LED outputs.'
        evidence = 'OGM-HardwareConfig/include/HardwareConfig/OpenKNX/Xiao.h'
        if 'KNEOPIX' in board:
            evidence += '; OpenKNX-KNeoPiX/Hardware/EDA-Files/Source/' + ('KNeoPiX_v1.3.kicad_sch; https://www.ti.com/product/TXS0108E' if board.endswith('_V1') else 'v1.5/KNeoPiX_v1.5.kicad_sch')
        wiki = {'ESP32S3': 'xiao_esp32s3_getting_started', 'RP2350': 'xiao_rp2350_arduino',
                'ESP32C5': 'xiao_esp32c5_getting_started', 'ESP32C6': 'xiao_esp32c6_getting_started'}
        if mcu in wiki:
            evidence += '; https://wiki.seeedstudio.com/' + wiki[mcu] + '/'
        return (access, text + ' ' + raw + ' Raw pads are 3.3 V only and may be obscured by the carrier: solder access is required. No JTAG/camera/add-on on claimed pads. Observe MCU boot straps; V1.5 contacts must never be connected to buffered LED terminals. Source-verified mapping; physical board test pending.', evidence)
    if 'UP1' in board:
        return ('isolated terminal', 'Rx/GPIO21 crosses a digital isolator; isolated-side supply and bias required. Tx/Out cannot be reversed. This is not a passive dry-contact input.',
                'OpenKNX-UP1/hardware/EDA-Files/UP1-GW-UART/uart.kicad_sch')
    if 'DEVICE_GL_C_017WL' in board:
        return ('DIY terminal', 'IO13 extended GPIO terminal; 3.3 V dry contact to GND. LED outputs and onboard relay IO18 are excluded.',
                'https://10558736.s21i.faiusr.com/61/ABUIABA9GAAg9YWsyAYoufKf6QM.pdf (manufacturer manual, p.2)')
    if board.startswith('DEVICE_GL_C_'):
        return ('none qualified', 'Headers name free/relay GPIOs but terminal-level input circuitry is not verified; no inputs offered. Program button remains reserved.',
                'OGM-HardwareConfig/include/HardwareConfig/Others/Gledopto.h')
    if 'QUINLED' in board:
        if 'DIG2GO' in board:
            return ('GPIO cable/header', 'Extra GPIO21/22/23/25; 3.3 V only. LED and relay connections excluded.', 'https://quinled.info/quinled-dig2go-pinout-guide/')
        if 'NEXT_2' in board:
            return ('button/QEXP/I2C connector', 'Button2 has hardware pullup. QEXP GPIO0 affects boot if held LOW. Button1 is reserved for programming. 3.3 V only.', 'https://quinled.info/dig-next-2-pinout-guide/')
        if 'OCTA' in board:
            return ('button/I2C header', 'Button1/GPIO34 reserved for programming; Button2/GPIO35 needs external bias. I2C may share LED8 (V1/V2) or SD (V4); unused peripherals only. QEXP/SD pins not offered until shared-device wiring is qualified.', 'https://quinled.info/quinled-dig-octa-brainboard-32-8l-pinout-guide/' if '_V4_' in board else 'https://quinled.info/quinled-dig-octa-brainboard-32-8l-v2-pinout-guide/')
        v4 = '_V4_' in board
        return ('GPIO pin header', ('Q1-Q4, 3.3 V only. I2C GPIO1/3 unavailable (UART0 debug). Q1R/LED terminals output-only.' if v4 else 'Raw Q1-Q4 only, never Q1R/LED outputs. GPIO12 must be LOW at reset; no external pullup. Observe installed pull resistors. AE+ excludes Q4/GPIO32 (microphone).') + ' Output/input overlap is checked.', 'https://quinled.info/quinled-dig-quad-pinout-guide/' if v4 else 'https://quinled.info/quinled-dig-quad-pinout-guide-v3/')
    raise ValueError('Unaudited board: ' + board)


def audit():
    pio = shutil.which('pio') or str(Path.home() / '.platformio/penv/bin/pio')
    config = json.loads(subprocess.check_output([pio, 'project', 'config', '--json-output'], cwd=ROOT, text=True))
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        source, binary = Path(tmp) / 'inputs.cpp', Path(tmp) / 'inputs'
        code = '#include <cstdio>\n#define LOW 0\n#define HIGH 1\n#include "HardwareConfig/Helpers/HardwareInputs.h"\nint main() { std::printf("%u\\n", (unsigned)DEVICE_HW_ID);\n'
        for n in range(1, 65):
            code += f'#if HW_INPUT_COUNT >= {n}\n std::printf("%d|%s|%d|%d\\n", (int)HW_INPUT_{n}_GPIO, HW_INPUT_{n}_LABEL, (int)HW_INPUT_{n}_MODE, (int)HW_INPUT_{n}_ONLEVEL);\n#endif\n'
        source.write_text(code + '}\n')
        cache = {}
        for section, options in config:
            if not section.startswith('env:release_'):
                continue
            flags = dict(options)['build_flags']
            definitions = re.findall(r'(?:^|\s)-D\s*((?:OKNXHW_|DEVICE_)[A-Za-z0-9_]+)', '\n'.join(flags))
            # These environments each identify one HardwareConfig board.
            board = next(d for d in definitions if not d.startswith('DEVICE_DISPLAY'))
            if board not in cache:
                result = subprocess.run(['c++', '-std=c++11', '-Werror', '-Wno-unknown-pragmas', '-I' + str(ROOT / 'lib/OGM-HardwareConfig/include'), '-D' + board, str(source), '-o', str(binary)], text=True, capture_output=True)
                if result.returncode:
                    raise RuntimeError(board + '\n' + result.stderr)
                cache[board] = subprocess.check_output([str(binary)], text=True).splitlines()
            connector, restrictions, evidence = notes(board)
            hardware_id, *connections = cache[board]
            for index, line in enumerate(connections or ['|||'], 1):
                gpio, label, bias, on = line.split('|')
                rows.append(dict(environment=section[4:], board=board, hardware_id=f'0x{int(hardware_id):04X}', input_port=index if gpio else '', gpio=gpio, label=label,
                                 bias=bias, active_high=on, access=connector, restrictions=restrictions, evidence=evidence))
    target = ROOT / 'test/hardware-input-audit.csv'
    with target.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Audited {len(cache)} boards / {len(set(r["environment"] for r in rows))} environments; {target}')


if __name__ == '__main__':
    audit()
