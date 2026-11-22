#include "hardware.h"
#if defined(NEOPIXEL_LOCAL_INPUTS) || defined(NEOPIXEL_LOCAL_INPUT_TEST) || defined(NEOPIXEL_INPUT_SIZE_TEST)
#include "NeoPixelInputs.h"
#include "OpenKNX.h"
#include "HardwareProfileData.h"
#include "GpioBinaryInputModule.h"
#include "HardwareConfig/Helpers/HardwarePorts.h"

namespace NeoPixelInputs
{
    static uint8_t inputPins[2] = {255, 255};

    bool claims(uint8_t gpio)
    {
        return gpio != 255 && (inputPins[0] == gpio || inputPins[1] == gpio);
    }

    void prepare()
    {
        uint8_t selections[2] = {255, 255};
        const bool enabled = knx.configured() && ParamBASE_ModuleEnabled_BI &&
                             HardwareProfile::selectionIsOwn(ParamNEOHW_HardwareSelect);
        for (uint8_t _channelIndex = 0; _channelIndex < 2; ++_channelIndex)
        {
            inputPins[_channelIndex] = 255;
            if (!enabled || !ParamBI_ChannelActive)
                continue;
            selections[_channelIndex] = ParamBI_ChannelPort;
            const uint8_t gpio = HardwareProfile::inputSignalGpio(ParamNEOHW_HardwareSelect, selections[_channelIndex]);
            if (gpio == 255 || HardwareProfile::isReservedGpio(gpio) || isHwRelayGpio(gpio))
            {
                logError("Inputs", "Input %u refused: unavailable or reserved connection", _channelIndex + 1);
                continue;
            }
            inputPins[_channelIndex] = gpio;
        }
        // Two inputs on one GPIO are both disabled, independently of registration order.
        if (inputPins[0] != 255 && inputPins[0] == inputPins[1])
        {
            logError("Inputs", "Both inputs refused: duplicate GPIO %u", inputPins[0]);
            inputPins[0] = inputPins[1] = 255;
        }
        for (uint8_t i = 0; i < 2; ++i)
        {
            const uint8_t bias = hwInputMode(selections[i]);
            const uint8_t mode = bias == 1 ? INPUT_PULLUP : bias == 2 ? INPUT_PULLDOWN : INPUT;
            openknxGpioBinaryInputModule.configureChannel(i, inputPins[i], mode, hwInputOnLevel(selections[i]) != 0);
        }
    }
}
#endif
