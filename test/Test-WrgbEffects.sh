#!/bin/sh
# Host exercise of the production effect and pixel buffer code.
set -eu
cd "$(dirname "$0")/.."
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/neopixel-render.XXXXXX")
trap 'rm -rf "$temp_dir"' EXIT
cat > "$temp_dir/Arduino.h" <<'STUB'
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
inline uint32_t millis() { return 0; }
STUB
cat > "$temp_dir/OpenKNX.h" <<'STUB'
#pragma once
#define logErrorP(...) ((void)0)
#define logDebugP(...) ((void)0)
#define logWarningP(...) ((void)0)
inline int freeMemory() { return 1024 * 1024; }
STUB
cat > "$temp_dir/HardwareConfig.h" <<'STUB'
#pragma once
#define HW_LEVELSHIFTER_NONE 0
#define HW_LEVELSHIFTER_TXS0108E 1
#define HW_LEVELSHIFTER_SN74HCT125 2
#define HW_LEVELSHIFTER_SN74AHCT125 3
#define HW_LEVELSHIFTER_SN74LV8T245 4
STUB
case "$(uname -s)" in
  Darwin) strip_flag=-Wl,-dead_strip ;;
  *) strip_flag=-Wl,--gc-sections ;;
esac
ofm_src=lib/OFM-NeoPixel/src
"${CXX:-c++}" -O2 -std=c++17 -ffunction-sections "$strip_flag" -I "$temp_dir" -I "$ofm_src" \
  test/test_wrgb_effects.cpp "$ofm_src/Segment.cpp" "$ofm_src/VirtualStrip.cpp" -o "$temp_dir/test-effects"
"$temp_dir/test-effects"
