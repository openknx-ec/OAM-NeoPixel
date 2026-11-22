#!/usr/bin/env python3
"""Compose the isolated input prototype and package its unsigned XKNX product."""
import argparse
from copy import deepcopy
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
NS = "http://knx.org/xml/project/20"
OP = "http://github.com/OpenKNX/OpenKNXproducer"
ENV = "inputtest_OKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15_IP"
ET.register_namespace("", NS)
ET.register_namespace("op", OP)


def write_xml(path, root):
    ET.indent(root, space="  ")
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n")


def prepare_wrappers(root=ROOT):
    """Generate application-owned wrappers around the reusable BinaryInput XML."""
    # Application-owned wrappers keep the reusable BI XML independent of NeoPixel.
    base = root / "lib/OFM-BinaryInput/src"
    help_dir = root / "src/Baggages/Help_de"
    help_dir.mkdir(parents=True, exist_ok=True)
    for help_file in (base / "Baggages/Help_de").glob("BI-*.md"):
        shutil.copy2(help_file, help_dir / help_file.name)
    share = (base / "BinaryInputChannel.share.xml").read_text()
    share = share.replace('href="BinaryInputChannel.templ.xml"', 'href="NeoPixel.BinaryInput.templ.generated.xml"')
    share = share.replace("</ParameterTypes>", '<op:include href="NeoPixel.inputs.gen.xml" xpath="//ApplicationProgram/Static/ParameterTypes/ParameterType" /></ParameterTypes>', 1)
    share = share.replace("</ParameterRefs>", '<op:include href="NeoPixel.FunctionBlocks.part.xml" xpath="//Block[@name=\'ModuleRefs\']/*" IsInner="true" /></ParameterRefs>', 1)
    (root / "src/NeoPixel.BinaryInput.share.generated.xml").write_text(share)
    template = (base / "BinaryInputChannel.templ.xml").read_text()
    template = template.replace("</Parameters>", '<op:include href="NeoPixel.inputs.gen.xml" xpath="//Block[@name=\'Parameters\']/*" /></Parameters>', 1)
    template = template.replace("</ParameterRefs>", '<op:include href="NeoPixel.inputs.gen.xml" xpath="//Block[@name=\'ParameterRefs\']/*" /></ParameterRefs>', 1)
    template = template.replace('<!-- Debounce -->', '<op:include href="NeoPixel.inputs.gen.xml" xpath="//Block[@name=\'Select\']/*" /><!-- Debounce -->', 1)
    (root / "src/NeoPixel.BinaryInput.templ.generated.xml").write_text(template)


def prepare(root=ROOT):
    prepare_wrappers(root)
    app = ET.parse(root / "src/NeoPixel-Dev.xml").getroot()
    version = app.find(f"{{{OP}}}ETS").get("ApplicationVersion")
    for config in app.findall(f"{{{OP}}}config"):
        if config.get("name") == "%NEO_ProductVersion%":
            config.set("value", f"{version} (Input-Test)")
    write_xml(root / "src/NeoPixel-InputTest.xml", app)

    profile = ET.parse(root / "HardwareManifest.xml").getroot()
    # The generator requires a hardware selection with at least two boards. Keep the
    # normal board IDs/slots for project migration and add the prototype env's pins.
    ET.SubElement(profile, "Boards", platformio="inputtest_*")
    ET.SubElement(profile, "Boards", platformio="inputsize_*")
    write_xml(root / "HardwareManifest.inputtest.generated.xml", profile)
    # Keep all existing board slot numbers, even though the prototype offers only this board.
    (root / "HardwareManifest.inputtest.generated.slots").write_bytes((root / "HardwareManifest.slots").read_bytes())


def bind(root=ROOT):
    """Bind the NEO-owned conflict flags into BI's channel template.

    Producer keeps the enclosing template's ModuleType even with include prefix=NEO.
    Resolve this boundary explicitly while leaving channel placeholders untouched.
    """
    conflicts = ET.parse(root / "src/NeoPixel.hw.conflicts.gen.xml").getroot()
    block = conflicts.find(f"{{{NS}}}Block[@name='ConflictChannel_Input']")
    assert block is not None
    app = ET.parse(root / "src/NeoPixel-Dev.xml").getroot()
    module_type = app.find(f"{{{OP}}}define[@prefix='NEO']").get("ModuleType")
    body = "".join(ET.tostring(child, encoding="unicode") for child in block)
    body = body.replace("%TT%", module_type)
    path = root / "src/NeoPixel.inputs.gen.xml"
    text = path.read_text()
    include = '<op:include href="NeoPixel.hw.conflicts.gen.xml" xpath="//Block[@name=\'ConflictChannel_Input\']/*" prefix="NEO" />'
    if include in text:
        path.write_text(text.replace(include, body))


def package(root=ROOT, application="NeoPixel-InputTest"):
    header = root / "include/knxprod.h"
    text = header.read_text(encoding="utf-8-sig")
    source_app = ET.parse(root / f"src/{application}.xml").getroot().find(f"{{{OP}}}ETS")
    major, minor = map(int, source_app.get("ApplicationVersion").split("."))
    version = major * 16 + minor
    for name, value in [("MAIN_ApplicationVersion", version), ("MAIN_ApplicationNumber", int(source_app.get("ApplicationNumber"))), ("BI_ChannelCount", 2), ("BTN_ChannelCount", 4)]:
        if not re.search(rf"^#define {name}\s+{value}\s*$", text, re.M):
            raise ValueError(f"Unexpected generated {name}; refusing mismatched prototype artifacts")
    marker = "#define NEOPIXEL_INPUTTEST_APPLICATION 1"
    if application == "NeoPixel-InputTest" and marker not in text:
        header.write_text(text + "\n" + marker + "\n", encoding="utf-8")
    source = ET.parse(root / f"src/{application}.debug.xml").getroot()
    manufacturer = source.find(f"{{{NS}}}ManufacturerData/{{{NS}}}Manufacturer")
    app = manufacturer.find(f"{{{NS}}}ApplicationPrograms")[0]
    if app.get("ApplicationVersion") != str(version):
        raise ValueError("Application XML does not match the input-test header")
    # XKNX's Python regex engine does not accept .NET's strict-end anchor \z.
    # The negative lookahead is an equivalent strict end in both engines.
    for node in app.iter():
        if "Pattern" in node.attrib:
            node.set("Pattern", node.get("Pattern").replace(r"\z", r"(?![\s\S])"))
    out = root / ("release/inputtest" if application == "NeoPixel-InputTest" else "release")
    out.mkdir(parents=True, exist_ok=True)
    product = out / f"{application}-xknx.knxprod"
    mid = manufacturer.get("RefId")
    with ZipFile(product, "w", ZIP_DEFLATED) as archive:
        for tag, filename in [("Catalog", "Catalog.xml"), ("Hardware", "Hardware.xml"),
                              ("Baggages", "Baggages.xml"), ("ApplicationPrograms", app.get("Id") + ".xml")]:
            node = manufacturer.find(f"{{{NS}}}{tag}")
            if node is None:
                continue
            document = ET.Element(source.tag, source.attrib)
            dest = ET.SubElement(ET.SubElement(document, f"{{{NS}}}ManufacturerData"), manufacturer.tag, manufacturer.attrib)
            dest.append(deepcopy(node))
            archive.writestr(mid + "/" + filename, ET.tostring(document, encoding="utf-8", xml_declaration=True))
        for file in (root / f"src/{application}.baggages").rglob("*"):
            if file.is_file():
                archive.write(file, mid + "/Baggages/" + file.relative_to(root / f"src/{application}.baggages").as_posix())
    print(f"Unsigned XKNX product: {product}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "prepare-shared", "bind", "package"])
    parser.add_argument("--application", choices=["NeoPixel-InputTest", "NeoPixel-Dev", "NeoPixel-Release"], default="NeoPixel-InputTest")
    args = parser.parse_args()
    if args.action == "package":
        package(application=args.application)
    else:
        {"prepare": prepare, "prepare-shared": prepare_wrappers, "bind": bind}[args.action]()
