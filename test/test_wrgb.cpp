#include "../src/StripConfiguration.h"
#include "SerialTimingProfile.h"

#include <array>
#include <cassert>
#include <initializer_list>

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

    for (size_t channel = 0; channel < 4; ++channel)
    {
        std::array<uint8_t, 4> logical{}, expected{}, wire{};
        logical[channel] = 255;
        expected[(channel + 1) % 4] = 255;
        assert(ProtocolHelper::orderChannels(ColorOrder::WRGB, logical[0], logical[1],
                                            logical[2], logical[3], 0, wire.data()) == 4);
        assert(wire == expected);
    }
}
