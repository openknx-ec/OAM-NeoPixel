// Behavioral checks of generated ETS conflict logic; run after Build-InputTest -SkipFirmware.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ctx = vm.createContext({});
vm.runInContext(fs.readFileSync('src/NeoPixel.hw.module.gen.js', 'utf8'), ctx);
const uses = ctx.NEOHW_conflictUses;
function flags(boardId, settings) {
    const board = ctx.NEOHW_conflictBoards[boardId];
    const input = {Sel: boardId, P_BIEnabled: 1, P_Input1Active: 1, P_Input2Active: 1, P_Strips: 0, P_Relays: 0};
    for (let i = 0; i < uses.length; ++i) input[`U${i}B${board.s}`] = 255;
    for (const [name, port] of Object.entries(settings.ports || {})) input[`U${uses.findIndex(u => u.n === name)}B${board.s}`] = port;
    Object.assign(input, settings.params || {});
    return Object.fromEntries(Array.from(ctx.NEOHW_conflictFlags(input), (flag, i) => [uses[i].n, flag]));
}
// C6 Mini: input terminal 1 is the same physical GPIO as output terminal 1.
let result = flags(0x1331, {ports: {Input1: 0, Strip1Data: 0}, params: {P_Strips: 1, P_Type1: 0}});
assert.equal(result.Input1, 1);
assert.equal(result.Strip1Data, 1);
result = flags(0x1322, {ports: {Input1: 0, Input2: 0}});
assert.equal(result.Input1, 1);
assert.equal(result.Input2, 1);
result = flags(0x1322, {ports: {Input1: 0, Input2: 1}});
assert.equal(result.Input1, 0);
assert.equal(result.Input2, 0);
result = flags(0x1322, {ports: {Input1: 0, Input2: 0}, params: {P_BIEnabled: 0}});
assert.equal(result.Input1, 0);
assert.equal(result.Input2, 0);
result = flags(0x1322, {ports: {Input1: 0, Input2: 0}, params: {P_Input2Active: 0}});
assert.equal(result.Input1, 0);
assert.equal(result.Input2, 0);
// Quad V3's raw Q1/GPIO15 can be used as input OR as the external relay.
result = flags(0x2120, {ports: {Input1: 0, Relay1: 4}, params: {P_Relays: 1}});
assert.equal(result.Input1, 1);
assert.equal(result.Relay1, 1);
assert.equal(ctx.NEOHW_conflictBoards[0x2120].inputs[3], 32, 'Q4 is GPIO32, never LED4/GPIO4');
// Invalid and unselected connections occupy no GPIO, including an unsupported Gledopto board.
assert.equal(flags(0x1322, {ports: {Input1: 64, Input2: 255}}).Input1, 0);
assert.equal(flags(0x2000, {ports: {Input1: 0}}).Input1, 0);
// Output sentinel values 10/15 are ordinary input-port indexes; only 255 is unused.
for (const port of [10, 15]) {
    result = flags(0x1311, {ports: {Input1: port, Input2: port}});
    assert.equal(result.Input1, 1);
    assert.equal(result.Input2, 1);
}
console.log('ETS input/output/relay conflicts, activation, invalid selections and Q4 mapping passed');
