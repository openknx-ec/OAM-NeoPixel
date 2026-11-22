#pragma once
#include <stdint.h>

namespace NeoPixelInputs
{
    // Resolve and claim configured inputs before any output module configures GPIOs.
    void prepare();
    bool claims(uint8_t gpio);
}
