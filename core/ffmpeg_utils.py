import os
import shutil
import imageio_ffmpeg

def get_ffmpeg_path() -> str:
    """
    Obtiene la ruta al binario ejecutable de FFmpeg.
    Primero busca en la carpeta local del proyecto (bin/ffmpeg.exe o ffmpeg.exe),
    luego el binario portable de imageio_ffmpeg, y finalmente el del sistema.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, "bin", "ffmpeg.exe"),
        os.path.join(base_dir, "ffmpeg.exe"),
        os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe"),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand

    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    
    system_exe = shutil.which("ffmpeg")
    if system_exe:
        return system_exe
        
    raise RuntimeError("No se encontró ningún ejecutable de FFmpeg en el sistema ni en imageio_ffmpeg.")
