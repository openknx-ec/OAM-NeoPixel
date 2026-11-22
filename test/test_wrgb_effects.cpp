#include "effects/CylonEffect.h"
#include "effects/SparkleEffect.h"
#include "effects/TwinkleFoxEffect.h"

#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>

namespace
{
    void setupScanner(Segment& segment, uint8_t mode, uint8_t speed, uint8_t size)
    {
        auto& cfg = segment.getConfig();
        cfg.mode = mode;
        cfg.speed = speed;
        cfg.option2 = size;
        cfg.option3 = 255;
        cfg.intensity = 255;
    }

    void checkPixels(const VirtualStrip& strip, uint16_t first, uint16_t second)
    {
        for (uint16_t i = 0; i < strip.getLedCount(); ++i)
            assert((strip.getBuffer()[i * strip.getBytesPerLed()] != 0) == (i == first || i == second));
    }

    void testScanner()
    {
        CylonEffect effect;
        for (const uint16_t n : {1, 2, 5, 6})
        {
            VirtualStrip strip(n, ColorOrder::RGB);
            Segment segment(&strip, 0, n - 1);
            setupScanner(segment, 2, 255, 1);
            for (uint16_t position = 0; position < n; ++position)
            {
                effect.update(&segment, position ? 5 : 0);
                checkPixels(strip, position, n - 1 - position);
            }

            VirtualStrip restarted(n, ColorOrder::RGB);
            Segment reverse(&restarted, 0, n - 1);
            setupScanner(reverse, 2, 0, 1);
            reverse.getConfig().reverse = true;
            effect.update(&reverse, 0);
            checkPixels(restarted, (n - 1) / 2, n / 2);
        }

        VirtualStrip matrix(10, ColorOrder::RGB);
        Segment segment(&matrix, 0, 9);
        segment.setGeometry(5, 2, LedTopology::ROWS_LINEAR);
        setupScanner(segment, 2, 255, 1);
        effect.update2D(&segment, 10);
        for (uint8_t y = 0; y < 2; ++y)
            for (uint8_t x = 0; x < 5; ++x)
                assert((matrix.getBuffer()[(y * 5 + x) * 3] != 0) == (x == 2));

        VirtualStrip empty(0, ColorOrder::RGB);
        Segment noPixels(&empty, 0, 0);
        effect.update(&noPixels, 5);
    }

    void testTwinkle()
    {
        TwinkleFoxEffect effect;
        VirtualStrip first(80, ColorOrder::RGBW), second(80, ColorOrder::RGBW);
        Segment regular(&first, 0, 79), irregular(&second, 0, 79);
        for (Segment* segment : {&regular, &irregular})
        {
            auto& cfg = segment->getConfig();
            cfg.mode = 3;
            cfg.speed = 96;
            cfg.option1 = 96;
            cfg.intensity = 255;
        }
        for (int i = 0; i < 10; ++i) effect.update(&regular, 20);
        effect.update(&irregular, 33);
        effect.update(&irregular, 167);
        assert(std::memcmp(first.getBuffer(), second.getBuffer(), first.getBufferSize()) == 0);

        bool lit = false, dark = false;
        for (uint16_t i = 0; i < first.getLedCount(); ++i)
        {
            const uint8_t* pixel = first.getBuffer() + i * 4;
            assert(pixel[0] == 0 && pixel[1] == 0 && pixel[2] == 0);
            lit |= pixel[3] > 0;
            dark |= pixel[3] == 0;
        }
        assert(lit && dark);

        effect.update(&regular, UINT32_MAX);
        effect.update(&regular, 1);
        effect.update(&irregular, 0);
        assert(std::memcmp(first.getBuffer(), second.getBuffer(), first.getBufferSize()) == 0);

        regular.getConfig().option1 = 0;
        regular.getConfig().option2 = 32;
        effect.update(&regular, 80);
        for (uint16_t i = 0; i < first.getLedCount(); ++i) assert(first.getBuffer()[i * 4 + 3] == 32);
    }

    double bench(Effect& effect, Segment& segment, uint8_t mode)
    {
        auto& cfg = segment.getConfig();
        cfg.mode = mode;
        cfg.intensity = 255;
        cfg.speed = 96;
        cfg.option1 = 96;
        cfg.option2 = 4;
        const auto start = std::chrono::steady_clock::now();
        constexpr int frames = 1500;
        for (int i = 0; i < frames; ++i) effect.update(&segment, 20);
        const auto elapsed = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - start);
        return elapsed.count() / frames;
    }
}

int main()
{
    testScanner();
    testTwinkle();

    CylonEffect cylon;
    SparkleEffect sparkle;
    TwinkleFoxEffect twinkle;
    for (const uint16_t count : {1, 2, 10, 80, 512})
    {
        VirtualStrip strip(count, ColorOrder::RGBW);
        Segment segment(&strip, 0, count - 1);
        std::printf("%3u LEDs, host µs per frame — Sparkle %.2f, Cylon %.2f/%.2f/%.2f, Twinklefox %.2f\n",
                    count, bench(sparkle, segment, 0), bench(cylon, segment, 0),
                    bench(cylon, segment, 1), bench(cylon, segment, 2), bench(twinkle, segment, 1));
    }
}
