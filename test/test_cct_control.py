#!/usr/bin/env python3
"""Run production CCT range, absolute control and dim steps with hardware doubles."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
STUBS = r'''
#include "IHardwareDriver.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <vector>
template<typename T> T constrain(T v, T lo, T hi) { return std::max(lo, std::min(hi, v)); }
struct ColorHelper { static void kelvinToRGB(uint16_t, uint8_t&, uint8_t&, uint8_t&) { assert(false); } };
struct Color { uint8_t ww=0,cw=0; uint16_t primaryKelvin=0; };
struct Segment {
    Color color;
    uint16_t getStartLed() const { return 10; }
    uint16_t getEndLed() const { return 29; }
    Color& getConfig() { return color; }
    void setPrimaryColor(uint8_t r,uint8_t g,uint8_t b,uint8_t ww,uint8_t cw) {
        assert(r==0 && g==0 && b==0);color.ww=ww;color.cw=cw;color.primaryKelvin=0;
    }
};
struct Strip {
    uint16_t warm, cool;
    bool native=true;
    bool hasDualWhiteChannel() const { return native; }
    uint16_t getWarmKelvin() const { return warm; }
    uint16_t getCoolKelvin() const { return cool; }
};
struct NeoPixelBusModule {
    struct SegmentConfig {
        enum DimmingChannel { CCT };
        Segment* segment;
        bool savedLastWasEffect=false;
        uint16_t dimmingCctPosition=0;
        uint8_t dimmingCctLevel=255;
        uint8_t brightness=91;
    };
    struct Mapping { size_t physicalStripIndex; uint16_t virtualStartPosition, ledCount; };
    std::vector<SegmentConfig> _segments;
    std::vector<Mapping> _virtualStripConfiguration;
    std::vector<Strip*> _physicalStrips;
    Strip* _virtualStrip;
    void cctRange(size_t,uint16_t&,uint16_t&) const;
    void applyCct(size_t,uint16_t,uint8_t=255);
    void captureDirectColor(size_t) {}
    void queueStatus(size_t,bool) {}
};
struct SegmentController {
    NeoPixelBusModule* _module;
    bool step(int16_t delta);
};
'''
TESTS = r'''
int main() {
    Segment segment;
    Strip first{2200,6000},second{2700,6500},irrelevant{5000,5500},third{7000,8000};
    NeoPixelBusModule module;
    module._segments.push_back({&segment});module._virtualStrip=&first;
    module._physicalStrips={&first,&second,&irrelevant,&third};
    module._virtualStripConfiguration={{0,10,10},{1,20,10},{2,40,10}};
    uint16_t warm,cool;module.cctRange(0,warm,cool);
    assert(warm==2700 && cool==6000);
    module.applyCct(0,2000);assert(segment.color.ww==255 && segment.color.cw==0 && segment.color.primaryKelvin==2700);
    module.applyCct(0,9000);assert(segment.color.ww==0 && segment.color.cw==255 && segment.color.primaryKelvin==6000);
    module.applyCct(0,4350,100);assert(segment.color.ww+segment.color.cw==100);
    auto& cfg=module._segments[0];cfg.dimmingCctPosition=128;cfg.dimmingCctLevel=100;
    SegmentController controller{&module};
    assert(!controller.step(10));assert(cfg.dimmingCctPosition==138 && cfg.brightness==91);
    assert(segment.color.ww+segment.color.cw==100);
    assert(controller.step(255));assert(cfg.dimmingCctPosition==255 && segment.color.cw==100);
    assert(controller.step(-255));assert(cfg.dimmingCctPosition==0 && segment.color.ww==100);
    // Three outputs with disjoint ranges fall back to the first native output's full range.
    module._virtualStripConfiguration.push_back({3,10,10});module.cctRange(0,warm,cool);
    assert(warm==2200 && cool==6000);
}
'''

def main():
    namespace = {'k': 'http://knx.org/xml/project/20'}
    schema = ET.parse(ROOT / 'src/NeoPixel.Strip.templ.xml')
    controls = {node.attrib['RefId'] for node in schema.findall('.//k:Dynamic//k:ParameterRefRef', namespace)}
    calculations = {node.attrib['RefId'] for node in schema.findall('.//k:ParameterCalculations//k:ParameterRefRef', namespace)}
    for suffix in ['083', '084']:
        reference = '%AID%_UP-%TT%9%C%' + suffix + '_R-%TT%9%C%' + suffix + '01'
        assert reference in controls and reference not in calculations
    source = (ROOT / 'src/NeoPixelModule.cpp').read_text()
    helpers = source[source.index('void NeoPixelBusModule::cctRange('):source.index('bool NeoPixelBusModule::processColourKo(')]
    controller = (ROOT / 'src/SegmentController.cpp').read_text()
    step = controller[controller.index('            case NeoPixelBusModule::SegmentConfig::CCT:'):controller.index('            case NeoPixelBusModule::SegmentConfig::RED:')]
    step = 'bool SegmentController::step(int16_t delta) { auto& segConfig=_module->_segments[0]; bool stepDone=false; switch(NeoPixelBusModule::SegmentConfig::CCT) {\n' + step + '} return stepDone; }\n'
    with tempfile.TemporaryDirectory(prefix='neopixel-cct-control-') as directory:
        path = Path(directory)
        (path / 'Arduino.h').write_text('#pragma once\n#include <cstdint>\n')
        (path / 'test.cpp').write_text(STUBS + helpers + step + TESTS)
        subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-fsanitize=address,undefined',
                        '-I' + str(path), '-I' + str(ROOT / 'lib/OFM-NeoPixel/src'), str(path / 'test.cpp'), '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)
    print('CCT range intersection, clipping, dim steps, brightness and disjoint outputs passed')

if __name__ == '__main__':
    main()
