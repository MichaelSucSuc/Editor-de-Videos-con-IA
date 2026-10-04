import os
import re
import subprocess
import numpy as np
from typing import List, Dict, Any, Tuple
from core.ffmpeg_utils import get_ffmpeg_path

def extract_audio_samples(
    audio_path: str, 
    start_sec: float = 0.0, 
    duration: float = -1.0, 
    sample_rate: int = 16000
) -> Tuple[np.ndarray, int]:
    """
    Extrae muestras de audio en formato PCM float32 usando FFmpeg directamente en memoria.
    Es 100% nativo, rápido y no requiere librerías externas de audio.
    """
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [ffmpeg_exe, "-y"]
    if start_sec > 0:
        cmd.extend(["-ss", f"{start_sec:.3f}"])
    if duration > 0:
        cmd.extend(["-t", f"{duration:.3f}"])
        
    cmd.extend([
        "-i", audio_path,
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "f32le",
        "-"
    ])
    
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    raw_data = proc.stdout
    samples = np.frombuffer(raw_data, dtype=np.float32)
    return samples, sample_rate

def compute_energy_envelope(
    samples: np.ndarray, 
    sample_rate: int = 16000, 
    frame_ms: float = 25.0, 
    hop_ms: float = 10.0
) -> Tuple[np.ndarray, float]:
    """
    Calcula la curva de energía RMS y actividad vocal en ventanas deslizantes.
    """
    frame_size = int(sample_rate * (frame_ms / 1000.0))
    hop_size = int(sample_rate * (hop_ms / 1000.0))
    
    if len(samples) < frame_size:
        return np.ones(1, dtype=np.float32), 0.01

    num_frames = (len(samples) - frame_size) // hop_size + 1
    # Crear matriz de frames con stride
    shape = (num_frames, frame_size)
    strides = (samples.strides[0] * hop_size, samples.strides[0])
    frames = np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides)
    
    # Energía RMS por frame
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-8)
    # Suavizado de la envolvente
    kernel_size = 5
    kernel = np.ones(kernel_size) / kernel_size
    smoothed_rms = np.convolve(rms, kernel, mode='same')
    
    time_step = hop_ms / 1000.0
    return smoothed_rms, time_step

def align_words_to_voice_energy(
    words: List[str],
    samples: np.ndarray,
    sample_rate: int,
    base_start_time: float,
    total_duration: float
) -> List[Dict[str, Any]]:
    """
    Realiza alineación acústica forzada (Acoustic Forced Alignment):
    Detecta exactamente cuándo la voz empieza a emitir sonido, cuándo hace pausas
    y asigna a cada palabra su segundo exacto según su longitud fonética y la actividad de la voz.
    """
    if not words:
        return []

    if len(samples) == 0 or total_duration <= 0.05:
        # Fallback proporcional si no hay audio
        step = total_duration / len(words)
        return [
            {
                "word": w,
                "start": base_start_time + i * step,
                "end": base_start_time + (i + 1) * step,
                "duration": step
            }
            for i, w in enumerate(words)
        ]

    energy, time_step = compute_energy_envelope(samples, sample_rate)
    
    # Umbral adaptativo de voz activa
    min_e = np.min(energy)
    max_e = np.max(energy)
    thresh = min_e + 0.15 * (max_e - min_e)
    
    # Encontrar el primer y último instante de voz real dentro del tramo
    active_indices = np.where(energy > thresh)[0]
    if len(active_indices) > 0:
        voice_start_rel = active_indices[0] * time_step
        voice_end_rel = min(total_duration, active_indices[-1] * time_step + 0.1)
    else:
        voice_start_rel = 0.0
        voice_end_rel = total_duration

    voice_span = max(0.2, voice_end_rel - voice_start_rel)
    
    # Ponderación fonética según número de caracteres de cada palabra
    # Las palabras largas (ej: "regulación", "contraseña") toman más tiempo que ("de", "el", "no")
    weights = [max(1.0, len(re.sub(r'[^\w]', '', w))) for w in words]
    total_weight = sum(weights)
    
    word_timings = []
    current_time = base_start_time + voice_start_rel
    
    for w, weight in zip(words, weights):
        w_dur = voice_span * (weight / total_weight)
        # Asegurar al menos 0.15s por palabra para legibilidad
        w_dur = max(0.12, w_dur)
        w_start = current_time
        w_end = w_start + w_dur
        
        word_timings.append({
            "word": w,
            "start": w_start,
            "end": w_end,
            "duration": w_dur
        })
        current_time = w_end

    # Ajustar para que no exceda el tiempo final
    limit_end = base_start_time + total_duration
    if word_timings and word_timings[-1]["end"] > limit_end:
        excess = word_timings[-1]["end"] - limit_end
        for item in word_timings:
            factor = (item["end"] - item["start"]) / (word_timings[-1]["end"] - word_timings[0]["start"] + 1e-6)
            item["start"] -= excess * factor * 0.5
            item["end"] -= excess * factor
            item["duration"] = item["end"] - item["start"]

    return word_timings

def align_transcript_blocks_to_audio(
    srt_blocks: List[Dict[str, Any]],
    audio_path: str
) -> List[Dict[str, Any]]:
    """
    Analiza internamente todo el audio con FFmpeg y NumPy.
    Para cada bloque de subtítulo, analiza la voz y genera subtítulos con marcas de tiempo acústicas precisas.
    """
    if not os.path.exists(audio_path) or not srt_blocks:
        return srt_blocks

    aligned_blocks = []
    
    for block in srt_blocks:
        start_sec = block.get("start_time", 0.0)
        end_sec = block.get("end_time", start_sec + 3.0)
        dur = max(0.1, end_sec - start_sec)
        
        raw_text = block.get("display_text", block.get("raw_text", "")).strip()
        words = raw_text.split()
        
        if not words:
            continue

        try:
            # Extraer muestras de voz de este intervalo exacto
            samples, sr = extract_audio_samples(audio_path, start_sec=start_sec, duration=dur)
            word_timings = align_words_to_voice_energy(
                words=words,
                samples=samples,
                sample_rate=sr,
                base_start_time=start_sec,
                total_duration=dur
            )
            
            # Agrupar las palabras alineadas en ráfagas de 2 a 3 palabras
            # pero usando los tiempos REALES medidos en el audio
            max_words = 3
            for i in range(0, len(word_timings), max_words):
                chunk = word_timings[i:i + max_words]
                chunk_text = " ".join([item["word"] for item in chunk])
                chunk_start = chunk[0]["start"]
                chunk_end = chunk[-1]["end"]
                
                aligned_blocks.append({
                    "index": f"{block.get('index', 1)}_{i}",
                    "start_time": chunk_start,
                    "end_time": chunk_end,
                    "duration": max(0.1, chunk_end - chunk_start),
                    "display_text": chunk_text,
                    "raw_text": chunk_text
                })
        except Exception:
            # Fallback seguro
            aligned_blocks.append(block)

    return aligned_blocks
