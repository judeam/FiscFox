# FiscFox App Icons

This directory contains app icons for desktop packaging.

## Files

- `icon.svg` - Source SVG icon (512x512 recommended for conversion)
- `icon.png` - Linux icon (256x256 PNG)
- `icon.ico` - Windows icon (multi-resolution .ico)
- `icon.icns` - macOS icon (Apple icon format)

## Generating Icons from SVG

### Linux (PNG)
```bash
# Using ImageMagick
convert -background none icon.svg -resize 256x256 icon.png

# Or using Inkscape
inkscape icon.svg -w 256 -h 256 -o icon.png
```

### Windows (ICO)
```bash
# Using ImageMagick (create multi-resolution)
convert icon.svg -define icon:auto-resize=256,128,64,48,32,16 icon.ico

# Or use online converter: https://cloudconvert.com/svg-to-ico
```

### macOS (ICNS)
```bash
# Create iconset directory
mkdir icon.iconset
sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png
sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     icon.png --out icon.iconset/icon_32x32.png
sips -z 64 64     icon.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   icon.png --out icon.iconset/icon_128x128.png
sips -z 256 256   icon.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   icon.png --out icon.iconset/icon_256x256.png
sips -z 512 512   icon.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   icon.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 icon.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
rm -rf icon.iconset
```

## Quick Start (Linux)

If you have ImageMagick installed:
```bash
cd assets
convert -background none icon.svg -resize 256x256 icon.png
```

Then build the desktop app:
```bash
make desktop-build
```
