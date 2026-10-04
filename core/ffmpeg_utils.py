import os
import shutil
import imageio_ffmpeg

def get_ffmpeg_path() -> str:
    """
    Obtiene la ruta al binario ejecutable de FFmpeg.
    Primero intenta usar el binario portable de imageio_ffmpeg, luego el del sistema.
    """
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
