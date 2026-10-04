import os
import subprocess
from core.ffmpeg_utils import get_ffmpeg_path

def master_voiceover_audio(
    input_audio_path: str,
    output_audio_path: str,
    preset: str = "viral_creator",
    target_lufs: float = -14.0
) -> str:
    """
    Calibra, ecualiza, comprime y masteriza profesionalmente la pista de voz para redes sociales:
    1. Filtro paso-alto (High-Pass 80Hz): Elimina ruidos graves de mesa, golpes de micrófono y zumbidos de baja frecuencia.
    2. Ecualización paramétrica de voz:
       - Atenúa la zona turbia/nasal (320 Hz) para mayor claridad.
       - Realza la presencia y articulación vocal (3.4 kHz) para que cada palabra se entienda con nitidez.
       - Añade brillo 'air' cristalino (10 kHz) estilo micrófono de condensador de estudio.
    3. Compresión dinámica (acompressor):
       - Iguala el volumen de la voz para que las palabras suaves se escuchen claras y las fuertes no saturen.
    4. Masterización de sonoridad comercial (EBU R128 loudnorm):
       - Normaliza a -14 LUFS con techo True-Peak de -1.5 dB (estándar oficial de TikTok, Reels y YouTube Shorts).
    """
    if not os.path.exists(input_audio_path):
        raise FileNotFoundError(f"No se encontró el archivo de audio: {input_audio_path}")

    ffmpeg_exe = get_ffmpeg_path()
    os.makedirs(os.path.dirname(os.path.abspath(output_audio_path)), exist_ok=True)

    # Cadena de filtros de audio profesional para voz
    filter_chain = (
        "highpass=f=80,"
        "equalizer=f=320:width_type=h:width=180:g=-2.5,"
        "equalizer=f=3400:width_type=h:width=1200:g=3.2,"
        "highshelf=f=10000:g=2.0,"
        "acompressor=threshold=-18dB:ratio=3.2:attack=8:release=60:makeup=2,"
        f"loudnorm=I={target_lufs}:TP=-1.5:LRA=7"
    )

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", input_audio_path,
        "-af", filter_chain,
        "-ar", "44100"
    ]
    if output_audio_path.lower().endswith(".mp3"):
        cmd.extend(["-c:a", "libmp3lame", "-b:a", "256k"])
    else:
        cmd.extend(["-c:a", "pcm_s16le"])
    cmd.append(output_audio_path)

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Error al masterizar el audio con FFmpeg:\n{proc.stderr}")

    return output_audio_path
