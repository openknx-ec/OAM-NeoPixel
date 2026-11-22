#include "../src/StripConfiguration.h"
#include "SerialTimingProfile.h"
#include "PowerManager.h"
#include "dptconvert.h"

#include <array>
#include <cassert>
#include <initializer_list>

void println(const char*) {} // KNX platform console is unused by these tests.

namespace
{
    struct Strip
    {
        ColorOrder order;
        ColorOrder getColorOrder() const { return order; }
    };

    uint8_t logicalWidth(std::initializer_list<const Strip*> strips)
    {
        return ProtocolHelper::getBytesPerLed(StripConfiguration::virtualColorOrder(strips));
    }
}

int main()
{
    const Strip rgb{ColorOrder::RGB}, rgbw{ColorOrder::RGBW}, grbw{ColorOrder::GRBW};
    const Strip wrgb{ColorOrder::WRGB}, rgbcct{ColorOrder::GRBCCT}, rgbctw{ColorOrder::RGBCTW};

    assert(logicalWidth({}) == 3);
    assert(logicalWidth({nullptr, &rgb}) == 3);
    assert(logicalWidth({&rgbw}) == 4);
    assert(logicalWidth({&grbw, &wrgb}) == 4);
    assert(logicalWidth({&wrgb}) == 4);
    assert(logicalWidth({&wrgb, &rgb}) == 4);
    assert(logicalWidth({&wrgb, &rgbcct}) == 5);
    assert(logicalWidth({&rgbctw, &wrgb}) == 5);

    assert(StripConfiguration::mapProtocol(8) == LedProtocol::SK6812);
    assert(StripConfiguration::mapProtocol(26) == LedProtocol::WS2814);
    assert(StripConfiguration::mapProtocol(31) == LedProtocol::WS2814_RGBCCT);
    assert(StripConfiguration::mapColorOrder(12) == ColorOrder::WRGB);
    static_assert(ProtocolHelper::getBytesPerLed(LedProtocol::WS2814) == 4);
    const auto ws2814 = SerialTiming::profileFor(LedProtocol::WS2814);
    assert(ws2814.t0h == 300 && ws2814.t0l == 950 && ws2814.t1h == 670 && ws2814.t1l == 580);

    for (uint8_t swap = 0; swap <= 3; ++swap)
    {
        uint8_t r = 0x11, g = 0x22, b = 0x33, w = 0x44, cw = 0;
        ProtocolHelper::applyChannelSwap(swap, r, g, b, w, cw);
        std::array<uint8_t, 4> wire{};
        ProtocolHelper::orderChannels(ColorOrder::WRGB, r, g, b, w, cw, wire.data());
        static constexpr std::array<uint8_t, 4> expected[] = {
            {0x44, 0x11, 0x22, 0x33},
            {0x33, 0x11, 0x22, 0x44},
            {0x22, 0x11, 0x44, 0x33},
            {0x11, 0x44, 0x22, 0x33},
        };
        assert(wire == expected[swap]);
    }

    PowerManager manager(1000);
    for (const uint16_t customCurrent : {0, 100})
    {
        manager.setCurrentPerLedMa(customCurrent);
        for (const auto protocol : {LedProtocol::SK6812, LedProtocol::WS2814})
        {
            const auto profile = manager.profileForProtocol(protocol);
            assert(profile.warmWhiteMA > 0 && profile.coolWhiteMA == 0);
            const uint8_t whiteOnly[] = {255, 0, 0, 0, 0, 0, 0, 0};
            assert(manager.calculateStripCurrent(whiteOnly, 2, protocol, ColorOrder::WRGB) == profile.warmWhiteMA);
        }
        assert(manager.profileForProtocol(LedProtocol::WS2812B).warmWhiteMA == 0);
        assert(manager.profileForProtocol(LedProtocol::WS2805_RGBCCT).coolWhiteMA > 0);
    }

    const std::array<uint8_t, 4> colors[] = {
        {255, 0, 0, 0}, {0, 255, 0, 0}, {0, 0, 255, 0}, {0, 0, 0, 255},
        {8, 64, 192, 240}, {0, 0, 0, 0},
    };
    for (const auto& logical : colors)
    {
        uint8_t incoming[] = {logical[0], logical[1], logical[2], logical[3], 0, 0x0f};
        KNXValue color(uint32_t{0});
        assert(KNX_Decode_Value(incoming, sizeof(incoming), DPT_Colour_RGBW, color));
        const uint32_t rgbw = color;
        std::array<uint8_t, 4> wire{};
        const std::array<uint8_t, 4> expected{logical[3], logical[0], logical[1], logical[2]};
        assert(ProtocolHelper::orderChannels(ColorOrder::WRGB, rgbw >> 24, rgbw >> 16,
                                            rgbw >> 8, rgbw, 0, wire.data()) == 4);
        assert(wire == expected);
        uint8_t status[6]{};
        assert(KNX_Encode_Value(color, status, sizeof(status), DPT_Colour_RGBW));
        for (size_t j = 0; j < sizeof(status); ++j) assert(status[j] == incoming[j]);
    }
}
