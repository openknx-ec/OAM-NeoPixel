#!/usr/bin/env python3
"""Exercise the production cue decoder against the ETS record layout."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'k': 'http://knx.org/xml/project/20'}


def main():
    cue_xml = ET.parse(ROOT / 'src/NeoPixel.Cue.part.xml')
    fields = {}
    for node in cue_xml.findall('.//k:Parameters/k:Parameter', NS):
        name = node.get('Name').removeprefix('NEOEM%C%Cue%CUE_NR%')
        if '%CUE_PPP+' in node.get('Id'):
            fields[name] = int(re.fullmatch(r'%CUE_OFF\+(\d+)%', node.get('Offset'))[1])
    expected = dict(Effect=0, PrimaryColor=11, PrimaryWW=14, PrimaryCW=15,
                    SecondaryColor=16, SecondaryWW=19, SecondaryCW=20,
                    Brightness=21, Duration=22, Fade=24, Text=26, EffectText=40)
    expected.update({f'Param{i}': 1 + i for i in range(10)})
    assert fields == expected
    for node in cue_xml.findall('.//k:Parameters/k:Parameter', NS):
        if node.get('Name').endswith('LaufschriftText'):
            assert node.get('Offset') == '%CUE_OFF+40%'
    em_xml = ET.parse(ROOT / 'src/NeoPixel.EM.templ.xml')
    op = {'op': 'http://github.com/OpenKNX/OpenKNXproducer'}
    part = em_xml.find('op:part', op)
    settings = {node.get('name'): node.attrib for node in part}
    assert settings['%CUE_OFF%']['value'] == '12' and settings['%CUE_OFF%']['increment'] == '54'
    assert settings['%CUE_PPP%']['value'] == '400' and settings['%CUE_PPP%']['increment'] == '22'
    assert '%CUE_EXT%' not in settings and '%CUE_SPP%' not in settings
    assert em_xml.find('.//k:Union', NS).get('SizeInBit') == str((12 + 10 * 54) * 8)
    source = (ROOT / 'src/NeoPixelModule.cpp').read_text()
    decoder = source[source.index('    auto loadCueFromEts ='):source.index('    if (!_emData) return; // EM table', source.index('    auto loadCueFromEts ='))]
    defines = '\n'.join(f'#define NEOEM_NEOEMCue1{name} {12 + offset}' for name, offset in fields.items())
    harness = r'''
#include "EffektManager.h"
#include <cassert>
#include <cstring>
#include <vector>
#define NEOEM_NEOEMCue2Effect 66
#define NEOEM_NEOEMCue1TextLength 14
#define NEOEM_NEOEMCue1EffectTextLength 14
#define NEOEM_ParamCalcIndex(field) ((field) + _channelIndex * 552)
struct Parameters {
    std::vector<uint8_t> data = std::vector<uint8_t>(16 * 552);
    uint8_t paramByte(size_t i) const { return data.at(i); }
    uint16_t paramWord(size_t i) const { return (uint16_t(data.at(i)) << 8) | data.at(i + 1); }
    const uint8_t* paramData(size_t i) const { return &data.at(i); }
};
uint8_t mapEtsEffectTypeToRuntimeIndex(uint8_t value) { return value; }
int main() {
    Parameters knx;
    uint8_t _channelIndex = 0;
    // Future header bytes must not affect decoding the following cues.
    for (size_t em = 0; em < 16; ++em)
        for (size_t byte = 4; byte < 12; ++byte) knx.data[em * 552 + byte] = 0xE5;
    for (size_t em = 0; em < 16; ++em) for (size_t index = 0; index < 10; ++index) {
        const size_t start = em * 552 + 12 + index * 54;
        for (uint8_t i = 0; i < 26; ++i) knx.data[start + i] = uint8_t(em * 10 + index + i);
        memcpy(&knx.data[start + 26], "12345678901234", 14);
        memcpy(&knx.data[start + 40], "abcdefghijklmn", 14);
    }
'''
    harness += decoder
    harness += r'''
    for (_channelIndex = 0; _channelIndex < 16; ++_channelIndex) for (uint8_t index = 0; index < 10; ++index) {
        EffektCue cue;
        loadCueFromEts(index, cue);
        const size_t start = size_t(_channelIndex) * 552 + 12 + size_t(index) * 54;
        assert(cue.effectId == knx.data[start]);
        for (uint8_t i = 0; i < EM_PARAM_COUNT; ++i) assert(cue.params[i] == knx.data[start + 1 + i]);
        assert(cue.primary.r == knx.data[start + 11] && cue.primary.b == knx.data[start + 13]);
        assert(cue.primary.ww == knx.data[start + 14] && cue.primary.cw == knx.data[start + 15]);
        assert(cue.secondary.r == knx.data[start + 16] && cue.secondary.b == knx.data[start + 18]);
        assert(cue.secondary.ww == knx.data[start + 19] && cue.secondary.cw == knx.data[start + 20]);
        assert(cue.brightness == knx.data[start + 21]);
        assert(cue.durationSec == knx.paramWord(start + 22) && cue.fadeMs == knx.paramWord(start + 24));
        assert(strcmp(cue.cueName, "12345678901234") == 0 && strcmp(cue.effectText, "abcdefghijklmn") == 0);
    }
}
'''
    with tempfile.TemporaryDirectory(prefix='neopixel-cue-layout-') as directory:
        path = Path(directory)
        (path / 'Arduino.h').write_text('#pragma once\n#include <cstdint>\n#define pgm_read_word(p) (*(p))\ninline uint32_t millis() { return 0; }\n')
        (path / 'HardwareConfig.h').write_text('#pragma once\n' + ''.join(f'#define HW_LEVELSHIFTER_{name} {i}\n' for i, name in enumerate(['NONE', 'TXS0108E', 'SN74HCT125', 'SN74AHCT125', 'SN74LV8T245'])))
        (path / 'test.cpp').write_text(defines + '\n' + harness)
        subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-fsanitize=address,undefined',
                        '-I' + str(path), '-I' + str(ROOT / 'lib/OFM-NeoPixel/src'), str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)
    print('All 160 cue records decoded with independent RGB/WW/CW colours and full fourteen-byte texts')


if __name__ == '__main__':
    main()
