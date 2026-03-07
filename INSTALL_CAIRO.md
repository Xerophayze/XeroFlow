# Installing Cairo for High-Quality SVG Rendering

## The Problem
The current implementation upscales low-resolution PNG images, which causes blurriness. To get sharp, high-quality diagrams, we need to convert SVG to PNG at high resolution using the Cairo library.

## Solution: Install GTK for Windows (includes Cairo)

### Option 1: Download GTK Binaries (Recommended)
1. Download GTK for Windows from: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
2. Run the installer (gtk3-runtime-x.x.x-x-x-x-ts-win64.exe)
3. Install to default location (C:\Program Files\GTK3-Runtime Win64)
4. Restart your terminal/IDE

### Option 2: Use MSYS2 (Alternative)
1. Download MSYS2 from: https://www.msys2.org/
2. Install MSYS2
3. Open MSYS2 terminal and run:
   ```bash
   pacman -S mingw-w64-x86_64-cairo
   ```
4. Add to PATH: C:\msys64\mingw64\bin

### Option 3: Manual Cairo DLL Installation
1. Download Cairo DLL from: https://github.com/preshing/cairo-windows/releases
2. Extract libcairo-2.dll to:
   - C:\Windows\System32 (for 64-bit)
   - Or add the folder to your PATH

## After Installation
Test that Cairo is working:
```python
import cairosvg
print("Cairo is working!")
```

## Current Workaround
The code currently falls back to upscaling low-resolution PNG images using Pillow's LANCZOS resampling. This works but produces slightly blurry results.

With Cairo installed, the code will automatically use high-quality SVG-to-PNG conversion at 4x scale, producing sharp, crisp diagrams.
