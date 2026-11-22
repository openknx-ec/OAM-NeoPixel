# WS2814 RGBW prüfen

Der BTF-FCOB-Streifen mit 24 V, 896 LEDs/m und 16 adressierbaren Gruppen pro Meter ergibt bei 5 m **80 Pixelgruppen** für ETS. Maßgeblich sind die Variante und das Schnittraster des verwendeten Streifens. [BTF-LIGHTING-Produktdaten](https://www.btf-lighting.com/en-intl/products/fcob-ws2814-rgbw-addressable-led-strip-dc24v-896leds)

1. Für den Farbtest den vorhandenen LED-Typ **SK6812/WS2814 (RGBW)** (8), **WRGB**, Kanaltausch **Keiner**, 24 V und die passende Gruppenanzahl eintragen. Ein Segment mit Solid konfigurieren. Für die Rohdatenprüfung Weißberechnung, HCL und Farbkalibrierung deaktivieren.
2. Jeweils genau Rot, Grün, Blau oder Warmweiß über den RGBW-Eingang (DPT 251.600) einschalten. Die Nummer des Eingangs und des Statusobjekts aus der geladenen Applikation ermitteln. Alternativ dieselben Kanäle mit `neo color 0 R G B W` prüfen.
3. Firmware- und Applikationsversion, `neo phys config 0 info` und `neo phys dump 0 0 8` sowie die sichtbare Farbe festhalten. Farbordnung bestimmt die Lage der Bytes. Kanaltausch vertauscht die Komponenten vor dem Packen.

| Kanal | WRGB bei voller Helligkeit |
|---|---|
| Rot | `00 FF 00 00` |
| Grün | `00 00 FF 00` |
| Blau | `00 00 00 FF` |
| Warmweiß | `FF 00 00 00` |

Danach lässt sich LED-Typ **WS2814 (RGBW, 4ch)** (26) separat mit denselben Einstellungen vergleichen. Nach dem Typwechsel WRGB erneut auswählen. Dieser Eintrag verwendet ein eigenes Pulsprofil und setzt die Farbordnung beim Wechsel zunächst gemäß dem generischen WS2814-Datenblatt auf RGBW. [Worldsemi WS2814-Datenblatt](https://www.signliteled.com/wp-content/uploads/2024/08/WS2814-Datasheet.pdf)

Die Strom- und Leistungs-KOs liefern **Schätzwerte**. Die 24-V-Angabe bestimmt die Umrechnung nach Watt. Die Stromannahme pro adressierbarer Gruppe sollte aus dem Datenblatt des Streifens oder aus einer Messung mit dem verwendeten Netzteil abgeleitet werden. Für den Vergleich das vierte Kanalbyte, Warmweiß allein, einen gemischten Farbwert sowie das globale und das streifenbezogene Stromlimit prüfen.

## Effekte

**Scanner Dual** ist Modus 2 von Cylon (Effekt 6). Zwei gespiegelte Augen laufen von den Enden aufeinander zu und durch die Mitte. Bei 2D bestimmt „Richtung“ die Achse. Dies entspricht der Bewegungsart von WLED Scanner Dual (60), während WLED Dual Scan (11) einen anderen Ablauf verwendet.

**Twinklefox** ist Effekt 33 für 1D. Die Lichtpunkte glimmen mit individuellen Phasen auf und ab. Geschwindigkeit, Dichte, Palette und Hintergrundhelligkeit sind als Parameter verfügbar. Die Warmweißpalette verwendet den Weißkanal eines RGBW- oder RGBCCT-Puffers. Auf RGB-Ausgängen verwendet sie einen warmen RGB-Farbton.

Beide Effekte sind eigenständig in OFM-NeoPixel implementiert. Die WLED-Effektnamen dienen als Referenz für das Verhalten. [WLED-Effektliste und Quellcode](https://github.com/wled/WLED/blob/main/wled00/FX.cpp)

## Hosttest

Unter macOS im Projektverzeichnis ausführen.

```sh
c++ -std=c++17 -ffunction-sections -Wl,-dead_strip \
  -I lib/OFM-NeoPixel/src -I lib/knx/src/knx \
  test/test_wrgb.cpp src/StripConfiguration.cpp \
  lib/knx/src/knx/{dpt,dptconvert,bits,knx_value}.cpp -o /tmp/neopixel-test-wrgb
/tmp/neopixel-test-wrgb
```

Unter Linux `-Wl,--gc-sections` verwenden.
