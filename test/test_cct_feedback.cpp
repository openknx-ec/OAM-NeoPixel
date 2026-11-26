#include "EffektManager.h"
#include "HclPixelTransform.h"
#include "effects/EffectSolid.h"
#include <cassert>

Effect* EffectPool::getEffectOrSolid(uint8_t)
{
    static EffectSolid solid;
    return &solid;
}

int main()
{
    // A cue must have identical colours after unrelated scenes, on restart and cue changes.
    VirtualStrip strip(4, ColorOrder::GRBCCT);
    Segment segment(&strip, 0, 3);
    EffektManagerData data[EM_COUNT]{};
    auto& em = data[0];
    em.header.enabled = 1;
    em.header.cueCount = 2;
    em.cues[0].primary = CueColor{1, 2, 3, 239, 17};
    em.cues[0].secondary.r = 12;
    em.cues[0].secondary.ww = 45;
    em.cues[0].secondary.cw = 67;
    // The second cue has two explicit black colours by default.
    EffektManagerController manager;
    segment.setSecondaryColor(255, 255, 255, 255, 255);
    manager.start(1, &segment, data);
    assert(segment.getConfig().r2() == 12 && segment.getConfig().ww2() == 45 && segment.getConfig().cw2() == 67);
    assert(segment.getConfig().ww() == 239 && segment.getConfig().cw() == 17);
    assert(manager.triggerCue(2, &segment, data));
    assert(segment.getSecondaryColor() == 0 && segment.getConfig().cw2() == 0);
    segment.setSecondaryColor(3, 4, 5, 6, 7);
    manager.restart(1, &segment, data);
    assert(segment.getConfig().r2() == 12 && segment.getConfig().cw2() == 67);
    // Single-white and RGB outputs never inherit a previous cool-white channel.
    VirtualStrip rgbw(4, ColorOrder::RGBW);
    Segment singleWhite(&rgbw, 0, 3);
    manager.stop(&segment, EM_STOP_LEAVE);
    manager.start(1, &singleWhite, data);
    assert(singleWhite.getConfig().ww() == 239 && singleWhite.getConfig().cw() == 0);
    assert(singleWhite.getConfig().ww2() == 45 && singleWhite.getConfig().cw2() == 0);
    manager.stop(&singleWhite, EM_STOP_LEAVE);
    manager.start(1, &segment, data);
    // Native colour setters relinquish a Kelvin target, direct-state restore retains it.
    manager.stop(&segment, EM_STOP_LEAVE);
    segment.getConfig().primaryKelvin = 4000;
    segment.saveDirectState();
    segment.setPrimaryColor(1, 2, 3, 4, 5);
    assert(segment.getConfig().primaryKelvin == 0);
    assert(segment.restoreDirectState() && segment.getConfig().primaryKelvin == 4000);

    uint8_t ww, cw;
    ProtocolHelper::kelvinToWWCW(2000, ww, cw, 2200, 6000);
    assert(ww == 255 && cw == 0);
    ProtocolHelper::kelvinToWWCW(4100, ww, cw, 2200, 6000);
    assert(ww + cw == 255 && cw == 127);
    ProtocolHelper::kelvinToWWCW(7000, ww, cw, 2200, 6000);
    assert(ww == 0 && cw == 255);

    HclTransformContext context;
    context.segments.push_back(&segment);
    context.pixelToSegmentIndex.assign(4, 0);
    context.segmentConfigs.resize(1);
    context.segmentConfigs[0].hclMode = NeoHclMode::Global;
    context.globalHclConfig.resolvedMaster = 1;
    auto& master = context.masterStates[0];
    master.blocked = false;
    uint8_t r = 0, g = 0, b = 0;
    ww = 0; cw = 100;
    master.kelvin = 2700;
    HclPixelTransform::Callback(0, r, g, b, &ww, &cw, &context);
    assert(ww == 100 && cw == 0 && r == 0 && g == 0 && b == 0);
    master.kelvin = 6500;
    HclPixelTransform::Callback(0, r, g, b, &ww, &cw, &context);
    assert(ww == 0 && cw == 100);
    master.kelvin = 4100;
    HclPixelTransform::CallbackForOutput(0, r, g, b, &ww, &cw, &context, 2200, 6000);
    assert(ww >= 49 && ww <= 51 && cw >= 49 && cw <= 51);
    ww = 0; cw = 100;
    master.blocked = true;
    master.kelvin = 2700;
    HclPixelTransform::Callback(0, r, g, b, &ww, &cw, &context);
    assert(ww == 0 && cw == 100);
}
