#include "../src/StripConfiguration.h"
#include "SerialTimingProfile.h"
#include "PowerManager.h"
#include "ProtocolTableAsserts.h"
#include "dptconvert.h"

#include <algorithm>
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

    void testFW1906()
    {
        const auto protocol = StripConfiguration::mapProtocol(15);
        assert(protocol == LedProtocol::FW1906);
        const auto explicitOrder = StripConfiguration::mapColorOrder(11);
        assert(explicitOrder == ColorOrder::GRBCTW);
        assert(StripConfiguration::mapColorOrder(13) == ColorOrder::NONE);
        const auto chipOrder = ProtocolHelper::getColorOrder(protocol);
        assert(chipOrder == explicitOrder);
        const Strip rgb{ColorOrder::RGB}, rgbw{ColorOrder::GRBW}, fw1906{chipOrder};
        assert(logicalWidth({&rgb, &rgbw, &fw1906}) == 5);

        const auto timing = SerialTiming::profileFor(protocol);
        assert(timing.resetUs == 300 && !timing.inverted);
        const auto rmt = SerialTiming::toTicks(timing, 25);
        assert(rmt.t0h == 16 && rmt.t0l == 34 && rmt.t1h == 32 && rmt.t1l == 18);
        const auto pio = SerialTiming::solvePio(timing, 133000000);
        assert(pio.valid && pio.realizedBit >= 1235 && pio.realizedBit <= 1265);

        constexpr size_t stride = ProtocolHelper::getBytesPerLed(LedProtocol::FW1906);
        using Pixel = std::array<uint8_t, stride>;
        const Pixel expected{0x22, 0x11, 0x33, 0x55, 0x44, 0};
        const Pixel full{255, 255, 255, 255, 255, 0};
        for (const size_t count : {2, 140})
        {
            // Guard bytes on both sides detect overruns at the first and last IC.
            std::array<uint8_t, 840 + 2> storage;
            storage.fill(0xA5);
            uint8_t* const payload = storage.data() + 1;
            assert(stride * count == (count == 2 ? 12 : 840));
            for (size_t i = 0; i < count; ++i)
                ProtocolHelper::encodeSerialPixel(payload + i * stride, protocol, chipOrder, 0,
                                                  i % 2 ? 255 : 0x11, i % 2 ? 255 : 0x22,
                                                  i % 2 ? 255 : 0x33, i % 2 ? 255 : 0x44, i % 2 ? 255 : 0x55);
            for (size_t i = 0; i < count; ++i)
            {
                const uint8_t* pixel = payload + i * stride;
                const auto& frame = i % 2 ? full : expected;
                assert(std::equal(frame.begin(), frame.end(), pixel));
            }
            assert(storage.front() == 0xA5 && payload[stride * count] == 0xA5);
        }

        Pixel pixel = full;
        const auto encode = [&](ColorOrder order, uint8_t swap, uint8_t r, uint8_t g,
                                uint8_t b, uint8_t ww, uint8_t cw) {
            ProtocolHelper::encodeSerialPixel(pixel.data(), protocol, order, swap, r, g, b, ww, cw);
        };
        for (size_t channel = 0; channel < 5; ++channel)
        {
            Pixel isolated{};
            isolated[channel] = 255;
            encode(chipOrder, 0, isolated[1], isolated[0], isolated[2], isolated[4], isolated[3]);
            assert(pixel == isolated);
        }
        encode(chipOrder, 1, 0x11, 0x22, 0x33, 0x44, 0x55);
        assert(pixel == (Pixel{0x22, 0x11, 0x44, 0x55, 0x33, 0}));
        encode(ColorOrder::GRBCCT, 0, 0x11, 0x22, 0x33, 0x44, 0x55);
        assert(pixel == (Pixel{0x22, 0x11, 0x33, 0x44, 0x55, 0}));
        encode(ColorOrder::RGBW, 0, 0x11, 0x22, 0x33, 0x44, 0);
        assert(pixel == (Pixel{0x11, 0x22, 0x33, 0x44, 0, 0}));
        encode(ColorOrder::RGB, 0, 0x11, 0x22, 0x33, 0, 0);
        assert(pixel == (Pixel{0x11, 0x22, 0x33, 0, 0, 0}));
        encode(chipOrder, 0, 0, 0, 0, 0, 0);
        assert(pixel == Pixel{});

        PowerManager power(1000);
        pixel.fill(255); // A nonzero padding byte must never affect measured current.
        assert(power.calculateStripCurrent(pixel.data(), 1, protocol, chipOrder) == 100);
        power.setCurrentPerLedMa(60);
        for (const auto order : {ColorOrder::NONE, chipOrder, ColorOrder::RGBW, ColorOrder::RGB})
            assert(power.calculateStripCurrent(pixel.data(), 1, protocol, order) == 60);
        const Pixel whites[] = {{0, 0, 0, 255, 0, 255}, {0, 0, 0, 0, 255, 255}};
        assert(power.calculateStripCurrent(whites[0].data(), 1, protocol, chipOrder) == 12);
        assert(power.calculateStripCurrent(whites[1].data(), 1, protocol, chipOrder) == 12);
    }
}

int main()
{
    testFW1906();

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
