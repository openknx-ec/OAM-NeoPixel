"""Native behavioral checks of the actual GPIO resolver and reusable BI implementation."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InputGpioRuntime(unittest.TestCase):
    def compile_run(self, files, source, extra=()):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name, contents in files.items():
                target = directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents)
            main = directory / 'main.cpp'
            main.write_text(source)
            output = directory / 'test'
            result = subprocess.run(['c++', '-std=c++11', '-I' + tmp, '-I' + str(ROOT / 'include'),
                                     '-I' + str(ROOT / 'src'), '-I' + str(ROOT / 'lib/OGM-HardwareConfig/include'),
                                     *extra, str(main), '-o', str(output)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(output)], check=True)

    def test_input_claims_match_hardware_activation_and_duplicates(self):
        files = {
            'hardware.h': '#pragma once\n#define NEOPIXEL_LOCAL_INPUT_TEST\n#define OKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15\n#define KNX_IP_WIFI\n#define MASK_VERSION 0x57B0\n#include "HardwareConfig.h"\n',
            'OpenKNX.h': '''#pragma once
#include <cstdint>
#define INPUT 0
#define INPUT_PULLUP 1
#define INPUT_PULLDOWN 2
struct Knx { bool loaded=true; bool configured() { return loaded; } } knx;
static bool moduleEnabled=true, active[2]={true,true};
static uint16_t selected=0x1322;
static uint8_t ports[2]={0,1};
#define ParamBASE_ModuleEnabled_BI moduleEnabled
#define ParamNEOHW_HardwareSelect selected
#define ParamBI_ChannelActive active[_channelIndex]
#define ParamBI_ChannelPort ports[_channelIndex]
#define logError(...) ((void)0)
''',
            'GpioBinaryInputModule.h': '''#pragma once
struct FakeInputs {
 unsigned pins[2]={255,255}; unsigned modes[2]={0,0}; bool high[2]={false,false};
 bool configureChannel(unsigned i, unsigned pin, unsigned mode, bool on) { pins[i]=pin; modes[i]=mode; high[i]=on; return true; }
} openknxGpioBinaryInputModule;
'''
        }
        self.compile_run(files, '''#include <cassert>
#include <cstdio>
#include "NeoPixelInputs.cpp"
int main() {
 NeoPixelInputs::prepare();
 assert(NeoPixelInputs::claims(41) && NeoPixelInputs::claims(42));
 assert(!NeoPixelInputs::claims(255) && !NeoPixelInputs::claims(2));
 assert(openknxGpioBinaryInputModule.modes[0] == INPUT_PULLUP);
 assert(!openknxGpioBinaryInputModule.high[0]);
 ports[1]=0; NeoPixelInputs::prepare();
 assert(!NeoPixelInputs::claims(41));
 assert(openknxGpioBinaryInputModule.pins[0]==255 && openknxGpioBinaryInputModule.pins[1]==255);
 ports[1]=1; active[1]=false; NeoPixelInputs::prepare();
 assert(NeoPixelInputs::claims(41) && !NeoPixelInputs::claims(42));
 selected=0x1320; NeoPixelInputs::prepare(); assert(!NeoPixelInputs::claims(41));
 selected=0x1322; moduleEnabled=false; NeoPixelInputs::prepare(); assert(!NeoPixelInputs::claims(41));
 moduleEnabled=true; knx.loaded=false; NeoPixelInputs::prepare(); assert(!NeoPixelInputs::claims(41));
 knx.loaded=true; ports[0]=255; NeoPixelInputs::prepare(); assert(!NeoPixelInputs::claims(255));
 ports[0]=64; NeoPixelInputs::prepare(); assert(openknxGpioBinaryInputModule.pins[0]==255);
}
''')

    def test_dynamic_binary_input_and_legacy_array(self):
        files = {
            'hardware.h': '''#pragma once
#define OPENKNX_BI_GPIO_COUNT 2
#define BI_ChannelCount 2
#ifdef LEGACY
#define OPENKNX_BI_GPIO_PINS 3,4
#else
#define OPENKNX_BI_GPIO_PINS 255,255
#define OPENKNX_BI_DYNAMIC_PINS
#endif
''',
            'OpenKNX.h': '''#pragma once
#include <cstdint>
#include <string>
#include <algorithm>
#define LOW 0
#define HIGH 1
#define INPUT 0
#define INPUT_PULLUP 1
#define INPUT_PULLDOWN 2
#define MIN(a,b) std::min(a,b)
#define MODULE_BinaryInput_Version "test"
#define logErrorP(...) ((void)0)
#define logInfoP(...) ((void)0)
namespace OpenKNX {
 class Channel { public: Channel(uint8_t index): _channelIndex(index) {} virtual void setup() {} virtual void loop() {} virtual const std::string name() { return ""; } protected: uint8_t _channelIndex; };
 class Module { public: virtual const std::string name() { return ""; } virtual const std::string version() { return ""; } virtual void setup() {} virtual void loop() {} };
}
struct Gpio { int writes=0, reads=0, lastPin=-1, lastMode=-1; bool level=false;
 void pinMode(int pin, int mode) { ++writes; lastPin=pin; lastMode=mode; }
 bool digitalRead(int pin) { ++reads; lastPin=pin; return level; }
};
struct Facade { Gpio gpio; } openknx;
static bool states[2]={false,false};
''',
            'OpenKNX/Module.h': '#pragma once\n#include "OpenKNX.h"\n'
        }
        source = '''#include <cassert>
#include "GpioBinaryInputModule.cpp"
BinaryInputChannel::BinaryInputChannel(uint8_t i): OpenKNX::Channel(i) {}
void BinaryInputChannel::setup() {}
void BinaryInputChannel::loop() {}
const std::string BinaryInputChannel::name() { return "test"; }
bool BinaryInputChannel::isActive() { return true; }
void BinaryInputChannel::setHardwareState(bool state) { states[_channelIndex]=state; }
int main() {
#ifndef LEGACY
 assert(!openknxGpioBinaryInputModule.configureChannel(2,41,INPUT_PULLUP,false));
 assert(!openknxGpioBinaryInputModule.configureChannel(1,256,INPUT_PULLUP,false));
 assert(!openknxGpioBinaryInputModule.configureChannel(1,42,99,false));
 assert(openknxGpioBinaryInputModule.configureChannel(0,255,INPUT,false));
 assert(openknxGpioBinaryInputModule.configureChannel(1,42,INPUT_PULLDOWN,true));
#endif
 openknxGpioBinaryInputModule.setup();
#ifdef LEGACY
 assert(openknx.gpio.writes==2 && openknx.gpio.lastPin==4 && openknx.gpio.lastMode==INPUT_PULLUP);
 openknxGpioBinaryInputModule.loop(); assert(states[0] && states[1]);
#else
 assert(openknx.gpio.writes==1 && openknx.gpio.lastPin==42 && openknx.gpio.lastMode==INPUT_PULLDOWN);
 assert(!openknxGpioBinaryInputModule.configureChannel(1,41,INPUT_PULLUP,false));
 openknx.gpio.level=true; openknxGpioBinaryInputModule.loop();
 assert(openknx.gpio.reads==1 && states[1]);
#endif
}
'''
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.compile_run(files, source, ['-I' + str(ROOT / 'lib/OFM-BinaryInput/src'), *(['-DLEGACY'] if legacy else [])])


if __name__ == '__main__':
    unittest.main()
