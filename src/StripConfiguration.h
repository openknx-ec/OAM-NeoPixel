#pragma once

#include "IHardwareDriver.h"
#include <cstdint>

/**
 * @brief ETS enum mapping helpers used by NeoPixelBusModule.
 */
class StripConfiguration
{
  public:
    /**
     * @brief Map ETS protocol parameter to LedProtocol enum
     * @param paramLedType ETS parameter value
     * @return LedProtocol enum value
     */
    static LedProtocol mapProtocol(uint8_t paramLedType);

    /**
     * @brief Map ETS color order parameter to ColorOrder enum
     * @param c ETS parameter value
     * @return ColorOrder enum value
     */
    static ColorOrder mapColorOrder(uint8_t c);

    /** Select a logical buffer format wide enough for the attached strips. */
    template <typename Strips>
    static ColorOrder virtualColorOrder(const Strips& strips)
    {
        ColorOrder format = ColorOrder::RGB;
        for (const auto* strip : strips)
        {
            if (!strip) continue;
            const ColorOrder order = strip->getColorOrder();
            if (ProtocolHelper::hasDualWhiteChannel(order)) return ColorOrder::GRBCCT;
            if (ProtocolHelper::hasWhiteChannel(order)) format = ColorOrder::RGBW;
        }
        return format;
    }

    /**
     * @brief Check if protocol requires SPI
     * @param protocol LedProtocol to check
     * @return true if SPI protocol, false otherwise
     */
    static bool isSpiProtocol(LedProtocol protocol);
};
