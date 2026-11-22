"""Builds the skin folder from src/: Tasks.ini (one meter per row slot), Tasks.lua and the grid tile.

Rainmeter only treats Lua strings as UTF-8 when the script file is UTF-16 LE, so the script is re-encoded here.
"""
import struct
import zlib
from pathlib import Path

ROWS = 12
HERE = Path(__file__).parent
SKIN = HERE / "Tasks"

HEAD = r"""[Rainmeter]
Update=1000
AccurateText=1
DynamicWindowSize=1
LeftMouseUpAction=["obsidian://open?vault=MyVault&file=ReadWrite/Memory/memory"]

[Metadata]
Name=Tasks
Information=Open tasks and events from the Knowledge Hub memory file.

[Variables]
MemoryFile=C:\path\to\your\vault\ReadWrite\Memory\memory.md
MemoryFolder=C:\path\to\your\vault\ReadWrite\Memory\
Width=320
MaxTasks=8
MaxEvents=4
Ink=230,236,234,255
Muted=147,163,166,255
Live=45,184,166,255

[MeasureFolder]
Measure=Plugin
Plugin=FileView
Path=#MemoryFolder#
ShowDotDot=0
ShowFolder=0
Extensions=md
Count=1

[MeasureMtime]
Measure=Plugin
Plugin=FileView
Path=[MeasureFolder]
Type=FileDate
DateType=Modified
Index=1

[MeasureScript]
Measure=Script
ScriptFile=#@#Tasks.lua

[sText]
FontFace=Segoe UI
FontSize=10
FontColor=#Ink#
AntiAlias=1
ClipString=1
Hidden=1
DynamicVariables=1

[sMono]
FontFace=Consolas
FontSize=8
FontColor=#Muted#
AntiAlias=1
Hidden=1
DynamicVariables=1

[MeterBg]
Meter=Shape
Shape=Rectangle 0,0,1,1 | StrokeWidth 0 | Fill Color 0,0,0,0
DynamicVariables=1

[MeterGrid]
Meter=Image
ImageName=#@#grid.png
Tile=1
X=1
Y=1
W=1
H=1
DynamicVariables=1

[MeterCanvas]
Meter=Shape
Shape=Rectangle 0,0,1,1 | StrokeWidth 0 | Fill Color 0,0,0,0
DynamicVariables=1

[MeterTitle]
Meter=String
MeterStyle=sText
FontFace=Georgia
FontSize=15
StringStyle=Bold
Text=Tasks
X=16
Y=11
Hidden=0

[MeterHeader]
Meter=String
MeterStyle=sMono
StringAlign=Right
X=304
Y=21
Hidden=0

[MeterLabel]
Meter=String
MeterStyle=sMono
FontColor=#Live#
Text=EVENTS

[MeterNote]
Meter=String
MeterStyle=sText
FontColor=#Muted#
StringStyle=Italic

[MeterFooter]
Meter=String
MeterStyle=sMono
StringAlign=Right
"""

ROW = """
[MeterRow{i}Text]
Meter=String
MeterStyle=sText

[MeterRow{i}Badge]
Meter=String
MeterStyle=sMono
"""


def png(w, h, pixel):
    raw = b"".join(b"\0" + b"".join(pixel(x, y) for x in range(w)) for y in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main():
    (SKIN / "Tasks.ini").write_text(HEAD + "".join(ROW.format(i=i) for i in range(1, ROWS + 1)), encoding="utf-16", newline="\r\n")
    lua = (HERE / "src" / "Tasks.lua").read_text(encoding="utf-8")
    (SKIN / "@Resources" / "Tasks.lua").write_text(lua, encoding="utf-16", newline="\r\n")
    line = bytes((255, 255, 255, 7))
    (SKIN / "@Resources" / "grid.png").write_bytes(
        png(22, 22, lambda x, y: line if x == 0 or y == 0 else b"\0\0\0\0"))


if __name__ == "__main__":
    main()
