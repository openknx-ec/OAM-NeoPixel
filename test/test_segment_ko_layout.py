#!/usr/bin/env python3
"""Check the generated ETS object table for contiguous segments and module collisions."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def check(variant):
    path = ROOT / f'src/NeoPixel-{variant}.debug.xml'
    if not path.exists():
        raise AssertionError(f'Generate {variant} application first: {path}')
    objects = {}
    reserved = {}
    names = {}
    for _, element in ET.iterparse(path, events=('end',)):
        if element.tag.endswith('}ComObject'):
            number, name = int(element.get('Number')), element.get('Name')
            assert number not in objects, (variant, number, objects.get(number), name)
            if re.fullmatch(r"NEO_\d+Reserve[1-5]", name):
                reserved[name] = dict(element.attrib)
            objects[number] = name
            names[name] = number
        element.clear()
    additions = ['CCTRel', 'SecondaryRGB', 'SecondaryRGBState', 'SecondaryWW',
                 'SecondaryWWState', 'SecondaryCW', 'SecondaryCWState']
    for segment in range(1, 17):
        first = 600 + (segment - 1) * 65
        assert names[f'NEO_{segment}SegmentPower'] == first
        assert all(objects[n].startswith(f'NEO_{segment}') for n in range(first, first + 65))
        for offset, suffix in enumerate(additions, 53):
            assert names[f'NEO_{segment}{suffix}'] == first + offset
        for slot in range(1, 6):
            name = f'NEO_{segment}Reserve{slot}'
            assert names[name] == first + 59 + slot
            assert all(reserved[name][flag] == 'Disabled' for flag in
                       ('ReadFlag', 'WriteFlag', 'CommunicationFlag', 'TransmitFlag', 'UpdateFlag', 'ReadOnInitFlag'))
    assert not any(name.startswith('NEOC_') for name in names)
    lmg = [number for number, name in objects.items() if name.startswith('LMG_')]
    assert min(lmg) == 1642 and max(lmg) == 1999, lmg
    assert names['NEO_16SecondaryCWState'] == 1634
    template = ET.parse(ROOT / 'src/NeoPixel.Segment.templ.xml')
    ns = {'k': 'http://knx.org/xml/project/20'}
    refs = template.findall('.//k:ComObjectRef', ns)
    assert not any(re.search(r'%CC%0(?:65|66|67|68|69)$', ref.get('RefId')) for ref in refs)
    assert max(objects) == 2057  # BI/BTN unchanged; the reserve does not raise the table maximum.
    print(f'{variant}: all 16 segments have 60 consecutive controls + five disabled reserve slots; no KO number collisions')


if __name__ == '__main__':
    check('Dev')
    check('Release')
