#include "../src/StripConfiguration.h"

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
