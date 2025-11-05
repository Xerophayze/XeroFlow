import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path
from typing import Optional

try:
    import urllib.request as urlreq
except Exception:  # pragma: no cover
    urlreq = None
import zipfile


def _run(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = proc.communicate(timeout=30)
        return proc.returncode, out or "", err or ""
    except Exception as e:  # pragma: no cover
        return 1, "", str(e)


def which_ffmpeg() -> Optional[str]:
    # Check PATH first
    for bin_name in ("ffmpeg", "avconv"):
        path = shutil.which(bin_name)
        if path:
            return path
    # Check project-local vendor path
    project_root = Path(__file__).resolve().parent.parent
    candidates = []
    if platform.system() == "Windows":
        candidates.append(project_root / "bin" / "ffmpeg" / "bin" / "ffmpeg.exe")
        candidates.append(project_root / "bin" / "ffmpeg" / "ffmpeg.exe")
    else:
        candidates.append(project_root / "bin" / "ffmpeg" / "bin" / "ffmpeg")
        candidates.append(project_root / "bin" / "ffmpeg" / "ffmpeg")
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _download(url: str, dest: Path) -> Path:
    if urlreq is None:
        raise RuntimeError("urllib is not available to download ffmpeg")
    with urlreq.urlopen(url) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return dest


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)


def _windows_install_ffmpeg(vendor_dir: Path) -> Optional[str]:
    # Try multiple reliable sources
    urls = [
        # Gyan.dev essentials build (stable URL)
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        # BtbN latest win64 GPL build
        "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
    ]
    _ensure_dir(vendor_dir)
    tmp_dir = vendor_dir / "_download"
    _ensure_dir(tmp_dir)
    last_error = None
    for url in urls:
        try:
            zip_file = tmp_dir / "ffmpeg.zip"
            _download(url, zip_file)
            # Extract
            extract_dir = tmp_dir / "unzipped"
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            _ensure_dir(extract_dir)
            _extract_zip(zip_file, extract_dir)
            # Find ffmpeg.exe inside extracted structure
            ffmpeg_path = None
            for p in extract_dir.rglob("ffmpeg.exe"):
                ffmpeg_path = p
                break
            if not ffmpeg_path:
                last_error = f"ffmpeg.exe not found in archive from {url}"
                continue
            # Place into vendor_dir/bin
            target_bin = vendor_dir / "bin"
            _ensure_dir(target_bin)
            # Copy ffmpeg.exe and related binaries (ffprobe.exe, etc.)
            for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                src = ffmpeg_path.parent / name
                if src.exists():
                    shutil.copy2(src, target_bin / name)
            # Also copy required DLLs from the same folder
            for dll in ffmpeg_path.parent.glob("*.dll"):
                try:
                    shutil.copy2(dll, target_bin / dll.name)
                except Exception:
                    pass
            return str(target_bin / "ffmpeg.exe")
        except Exception as e:  # pragma: no cover (network-dependent)
            last_error = str(e)
            continue
    if last_error:
        print(f"[ffmpeg_installer] Windows ffmpeg download failed: {last_error}")
    return None


def _linux_mac_install_ffmpeg() -> bool:
    # Try to install via popular package managers. We won't use sudo automatically in case permissions are restricted.
    # Instead, try without sudo first, then with sudo if available.
    cmds = []
    if platform.system() == "Darwin":
        if shutil.which("brew"):
            cmds.append(["brew", "install", "ffmpeg"])
    else:
        if shutil.which("apt-get"):
            cmds.append(["sudo", "apt-get", "update"])  # best-effort, ignore failures
            cmds.append(["sudo", "apt-get", "install", "-y", "ffmpeg"])
        if shutil.which("dnf"):
            cmds.append(["sudo", "dnf", "install", "-y", "ffmpeg"])
        if shutil.which("yum"):
            cmds.append(["sudo", "yum", "install", "-y", "ffmpeg"])
        if shutil.which("pacman"):
            cmds.append(["sudo", "pacman", "-Syu", "--noconfirm", "ffmpeg"])
        if shutil.which("zypper"):
            cmds.append(["sudo", "zypper", "install", "-y", "ffmpeg"])
    success = False
    for cmd in cmds:
        code, _, _ = _run(cmd)
        # Don't break on update failure; see if later command succeeds
        if "install" in cmd:
            if code == 0 and which_ffmpeg():
                success = True
                break
    return success


def ensure_ffmpeg_available(auto_install: bool = True) -> Optional[str]:
    """
    Ensure ffmpeg (or avconv) is available.
    - Returns the absolute path to the found/installed ffmpeg binary when available.
    - If not found and auto_install is False, returns None.
    - If auto_install is True, attempts to install (Windows: vendor download, Linux/macOS: package manager).
    - Also prepends the project-local vendor bin path to PATH for current process if installed.
    """
    found = which_ffmpeg()
    if found:
        # Prepend containing directory to PATH so sub-processes see it consistently
        bin_dir = str(Path(found).parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return found

    if not auto_install:
        return None

    system = platform.system()
    project_root = Path(__file__).resolve().parent.parent
    vendor_dir = project_root / "bin" / "ffmpeg"

    installed_path = None
    if system == "Windows":
        installed_path = _windows_install_ffmpeg(vendor_dir)
    else:
        # Try package manager
        if _linux_mac_install_ffmpeg():
            installed_path = which_ffmpeg()
        else:
            # Fallback: instruct user but still return None
            print("[ffmpeg_installer] Could not auto-install ffmpeg. Please install it via your package manager.")
            installed_path = None

    if installed_path:
        bin_dir = str(Path(installed_path).parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return installed_path
