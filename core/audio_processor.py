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

    # Cadena de filtros de audio profesional para voz en redes sociales (TikTok / Reels / Shorts)
    # 1. Highpass 80Hz para eliminar ruidos de fondo y graves
    # 2. Ecualización paramétrica: limpia frecuencias nasales (320Hz) y potencia presencia/articulación (3.4kHz y 10kHz)
    # 3. Dynamic Audio Normalizer (dynaudnorm): eleva palabras bajas y homogeneiza la voz para claridad total
    # 4. Limitador transparente para picos bruscos
    # 5. Normalización EBU R128 a volumen comercial óptimo (-12.5 a -13.0 LUFS)
    filter_chain = (
        "highpass=f=80,"
        "equalizer=f=320:width_type=h:width=180:g=-2.5,"
        "equalizer=f=3400:width_type=h:width=1200:g=3.8,"
        "highshelf=f=10000:g=2.8,"
        "dynaudnorm=f=120:g=15:p=0.95:m=6.0,"
        "alimiter=limit=0.92:attack=5:release=50,"
        f"loudnorm=I={target_lufs}:TP=-0.8:LRA=6:dual_mono=true"
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


def mix_voiceover_with_bgm(
    voice_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume: float = 0.15,
    enable_ducking: bool = True
) -> str:
    """
    Mezcla la voz principal con música de fondo (BGM):
    - Si enable_ducking es True, aplica compresión lateral (sidechain) automática:
      la música baja automáticamente a volumen suave cuando el locutor habla y sube en las pausas.
    - La música se reproduce en bucle continuo de forma transparente.
    """
    if not os.path.exists(voice_path):
        raise FileNotFoundError(f"No se encontró el audio de voz: {voice_path}")
    if not bgm_path or not os.path.exists(bgm_path):
        return voice_path

    ffmpeg_exe = get_ffmpeg_path()
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if enable_ducking:
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e+09,volume={bgm_volume}[bgm_loop];"
            f"[bgm_loop][0:a]sidechaincompress=threshold=0.08:ratio=5:attack=40:release=300[ducked];"
            f"[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=2"
        )
    else:
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e+09,volume={bgm_volume}[bgm_loop];"
            f"[0:a][bgm_loop]amix=inputs=2:duration=first:dropout_transition=2"
        )

    cmd = [
        ffmpeg_exe, "-y",
        "-i", voice_path,
        "-i", bgm_path,
        "-filter_complex", filter_complex,
        "-c:a", "pcm_s16le",
        "-ar", "44100",
        output_path
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Error al mezclar música de fondo con FFmpeg:\n{proc.stderr}")

    return output_path


def add_transition_sfx_to_audio(
    audio_path: str,
    output_path: str,
    transition_timestamps: list,
    sfx_path: str = None,
    sfx_volume: float = 0.35
) -> str:
    """
    Inyecta efectos de sonido 'Whoosh' en los momentos exactos de cada transición visual entre imágenes/videos.
    """
    if not os.path.exists(audio_path) or not transition_timestamps:
        return audio_path

    if sfx_path is None or not os.path.exists(sfx_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sfx_path = os.path.join(base_dir, "assets", "sfx", "whoosh.wav")

    if not os.path.exists(sfx_path):
        return audio_path

    import wave
    import numpy as np

    ffmpeg_exe = get_ffmpeg_path()
    temp_wav = output_path + ".temp_sfx_base.wav"
    subprocess.run([
        ffmpeg_exe, "-y", "-i", audio_path,
        "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le",
        temp_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        with wave.open(temp_wav, "r") as wf:
            voice_samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).copy()
            sr = wf.getframerate()

        with wave.open(sfx_path, "r") as wf_sfx:
            sfx_samples = np.frombuffer(wf_sfx.readframes(wf_sfx.getnframes()), dtype=np.int16)

        scaled_sfx = (sfx_samples.astype(np.float32) * sfx_volume).astype(np.float32)
        sfx_len = len(scaled_sfx)

        voice_float = voice_samples.astype(np.float32)
        for t in transition_timestamps:
            if t <= 0.2:
                continue
            idx = int((t - 0.10) * sr)
            if idx < 0:
                idx = 0
            if idx < len(voice_float):
                end_idx = min(len(voice_float), idx + sfx_len)
                sfx_slice_len = end_idx - idx
                voice_float[idx:end_idx] += scaled_sfx[:sfx_slice_len]

        np.clip(voice_float, -32767.0, 32767.0, out=voice_float)
        final_samples = voice_float.astype(np.int16)

        with wave.open(output_path, "w") as out_wf:
            out_wf.setnchannels(1)
            out_wf.setsampwidth(2)
            out_wf.setframerate(sr)
            out_wf.writeframes(final_samples.tobytes())

        return output_path
    finally:
        if os.path.exists(temp_wav):
            try:
                os.remove(temp_wav)
            except Exception:
                pass
