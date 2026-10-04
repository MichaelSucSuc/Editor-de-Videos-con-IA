import os
import re
import json
import unicodedata
import subprocess
import difflib
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from core.ffmpeg_utils import get_ffmpeg_path
from core.srt_engine import format_srt_timestamp

# Variable global para no recargar el modelo Vosk múltiples veces en la misma sesión
_GLOBAL_VOSK_MODEL = None

def get_vosk_model():
    """
    Carga el modelo acústico en español de Vosk en memoria (singleton).
    Descargado y almacenado localmente en caché.
    """
    global _GLOBAL_VOSK_MODEL
    if _GLOBAL_VOSK_MODEL is None:
        import vosk
        vosk.SetLogLevel(-1)
        _GLOBAL_VOSK_MODEL = vosk.Model(lang="es")
    return _GLOBAL_VOSK_MODEL

def normalize_word(text: str) -> str:
    """Limpia puntuación, diacríticos/acentos y normaliza a minúsculas para comparar."""
    if not text:
        return ""
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')
    return re.sub(r'[^\w]', '', text).lower()

def extract_vosk_word_timestamps(audio_path: str, progress_callback=None) -> List[Dict[str, Any]]:
    """
    Analiza la pista de audio con el modelo de reconocimiento acústico Vosk
    y devuelve la lista de todas las palabras habladas con su milisegundo exacto de inicio y fin.
    """
    if not os.path.exists(audio_path):
        return []

    import vosk
    model = get_vosk_model()
    recognizer = vosk.KaldiRecognizer(model, 16000)
    recognizer.SetWords(True)

    ffmpeg_exe = get_ffmpeg_path()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", audio_path,
        "-ar", "16000",
        "-ac", "1",
        "-f", "s16le",
        "-"
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    detected_words = []

    try:
        bytes_read = 0
        while True:
            data = proc.stdout.read(4000)
            if not data:
                break
            bytes_read += len(data)
            if recognizer.AcceptWaveform(data):
                res = json.loads(recognizer.Result())
                if "result" in res:
                    detected_words.extend(res["result"])

        final_res = json.loads(recognizer.FinalResult())
        if "result" in final_res:
            detected_words.extend(final_res["result"])
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait()

    return detected_words

def align_words_to_vosk(
    script_words: List[str], 
    vosk_words: List[Dict[str, Any]], 
    total_audio_duration: float = 0.0
) -> List[Dict[str, Any]]:
    """
    Alinea una lista de palabras de un guion/texto con los tiempos acústicos reales de Vosk.
    Usa coincidencia de secuencias (difflib) para anclar puntos clave e intercala el resto
    sobre la línea de tiempo fonética real sin desfases acumulativos.
    """
    if not vosk_words:
        # Fallback sin Vosk: distribución uniforme
        res = []
        cur = 0.0
        step = max(0.2, (total_audio_duration / max(1, len(script_words)))) if total_audio_duration > 0 else 0.35
        for w in script_words:
            res.append({"word": w, "start": cur, "end": cur + step})
            cur += step
        return res

    norm_s = [normalize_word(w) for w in script_words]
    norm_v = [normalize_word(w["word"]) for w in vosk_words]

    matcher = difflib.SequenceMatcher(None, norm_s, norm_v)
    matches = matcher.get_matching_blocks()

    aligned_words: List[Optional[Dict[str, Any]]] = [None] * len(script_words)
    anchors = []

    for m in matches:
        if m.size == 0:
            continue
        for k in range(m.size):
            s_i = m.a + k
            v_i = m.b + k
            vw = vosk_words[v_i]
            aligned_words[s_i] = {
                "word": script_words[s_i],
                "start": float(vw["start"]),
                "end": float(vw["end"])
            }
            anchors.append((s_i, v_i))

    # Si hay muy pocas coincidencias exactas (menos del 20%), mapear proporcionalmente
    if len(anchors) < max(2, int(len(script_words) * 0.20)):
        res = []
        n_vosk = len(vosk_words)
        n_script = len(script_words)
        for i, sw in enumerate(script_words):
            ratio = i / max(1, n_script - 1) if n_script > 1 else 0.0
            v_idx = int(round(ratio * (n_vosk - 1)))
            vw = vosk_words[min(n_vosk - 1, max(0, v_idx))]
            res.append({
                "word": sw,
                "start": float(vw["start"]),
                "end": float(vw["end"])
            })
        return res

    # Interpolar palabras antes del primer anchor
    first_s, first_v = anchors[0]
    if first_s > 0:
        if first_v > 0:
            for i in range(first_s):
                v_target = int(round(i * (first_v - 1) / max(1, first_s - 1))) if first_s > 1 else 0
                vw = vosk_words[min(first_v - 1, max(0, v_target))]
                aligned_words[i] = {"word": script_words[i], "start": float(vw["start"]), "end": float(vw["end"])}
        else:
            t_first = float(vosk_words[0]["start"])
            t_start = max(0.0, t_first - 0.35 * first_s)
            span = max(0.1, t_first - t_start)
            step = span / first_s
            for i in range(first_s):
                aligned_words[i] = {
                    "word": script_words[i], 
                    "start": t_start + i * step, 
                    "end": t_start + (i + 1) * step
                }

    # Interpolar palabras entre anchors consecutivos
    for a_idx in range(len(anchors) - 1):
        s_curr, v_curr = anchors[a_idx]
        s_next, v_next = anchors[a_idx + 1]
        gap_s = s_next - s_curr - 1
        gap_v = v_next - v_curr - 1

        if gap_s <= 0:
            continue

        if gap_v > 0:
            for step_i in range(1, gap_s + 1):
                s_i = s_curr + step_i
                v_target = v_curr + int(round(step_i * gap_v / (gap_s + 1)))
                vw = vosk_words[min(v_next - 1, max(v_curr + 1, v_target))]
                aligned_words[s_i] = {"word": script_words[s_i], "start": float(vw["start"]), "end": float(vw["end"])}
        else:
            t_s = aligned_words[s_curr]["end"]
            t_e = aligned_words[s_next]["start"]
            if t_e <= t_s:
                t_e = t_s + 0.3 * gap_s
            span = t_e - t_s
            weights = [max(1, len(script_words[s_curr + step_i])) for step_i in range(1, gap_s + 1)]
            tot_w = sum(weights)
            cur_t = t_s
            for step_i in range(1, gap_s + 1):
                s_i = s_curr + step_i
                dur = span * (weights[step_i - 1] / tot_w)
                aligned_words[s_i] = {"word": script_words[s_i], "start": cur_t, "end": cur_t + dur}
                cur_t += dur

    # Interpolar palabras después del último anchor
    last_s, last_v = anchors[-1]
    if last_s < len(script_words) - 1:
        rem_s = len(script_words) - 1 - last_s
        rem_v = len(vosk_words) - 1 - last_v
        if rem_v > 0:
            for step_i in range(1, rem_s + 1):
                s_i = last_s + step_i
                v_target = last_v + int(round(step_i * rem_v / rem_s))
                vw = vosk_words[min(len(vosk_words) - 1, v_target)]
                aligned_words[s_i] = {"word": script_words[s_i], "start": float(vw["start"]), "end": float(vw["end"])}
        else:
            t_s = aligned_words[last_s]["end"]
            t_e = max(t_s + 0.35 * rem_s, total_audio_duration if total_audio_duration > t_s else t_s + 1.5)
            span = t_e - t_s
            step = span / rem_s
            for step_i in range(1, rem_s + 1):
                s_i = last_s + step_i
                aligned_words[s_i] = {"word": script_words[s_i], "start": t_s + (step_i - 1) * step, "end": t_s + step_i * step}

    # Asegurar orden estrictamente no solapado
    final_list: List[Dict[str, Any]] = []
    for i in range(len(aligned_words)):
        item = aligned_words[i]
        if item is None:
            continue
        if final_list:
            prev = final_list[-1]
            if item["start"] < prev["start"]:
                item["start"] = prev["end"]
            if item["end"] <= item["start"]:
                item["end"] = item["start"] + 0.18
        final_list.append(item)

    return final_list

def transcribe_audio_to_srt(
    audio_path: str,
    max_words_per_chunk: int = 3,
    existing_script: str = "",
    total_duration: float = 0.0
) -> str:
    """
    Transcribe el audio usando Vosk y genera un archivo/cadena de texto en formato SRT estándar
    con marcas de tiempo acústicas exactas (milisegundo a milisegundo).
    Si se proporciona un guion existente, alinea el guion con las marcas detectadas.
    """
    vosk_words = extract_vosk_word_timestamps(audio_path)
    if not vosk_words:
        return ""

    if existing_script and existing_script.strip():
        script_words = existing_script.strip().split()
        timed_words = align_words_to_vosk(script_words, vosk_words, total_duration)
    else:
        timed_words = [
            {"word": vw["word"], "start": float(vw["start"]), "end": float(vw["end"])}
            for vw in vosk_words
        ]

    if not timed_words:
        return ""

    step = max(1, max_words_per_chunk) if max_words_per_chunk > 0 else len(timed_words)
    srt_lines = []
    chunk_idx = 1

    for i in range(0, len(timed_words), step):
        chunk = timed_words[i:i + step]
        start_t = chunk[0]["start"]
        end_t = chunk[-1]["end"]
        
        # Evitar duración 0
        if end_t <= start_t:
            end_t = start_t + 0.3

        chunk_text = " ".join([c["word"] for c in chunk])
        
        srt_lines.append(f"{chunk_idx}")
        srt_lines.append(f"{format_srt_timestamp(start_t)} --> {format_srt_timestamp(end_t)}")
        srt_lines.append(f"{chunk_text}\n")
        chunk_idx += 1

    return "\n".join(srt_lines)

def align_transcript_with_acoustic_analysis(
    srt_blocks: List[Dict[str, Any]],
    audio_path: str,
    max_words_per_chunk: int = 3
) -> List[Dict[str, Any]]:
    """
    Analiza verdaderamente la voz en el audio usando el modelo de reconocimiento Vosk:
    1. Extrae los tiempos reales de cada palabra que sale de la boca del locutor.
    2. Hace coincidir el texto del guion con los tiempos acústicos reales.
    3. Si alguna sección no tiene coincidencia fonética, usa el mapa de energía acústica como respaldo.
    """
    if not os.path.exists(audio_path):
        return srt_blocks

    try:
        vosk_words = extract_vosk_word_timestamps(audio_path)
    except Exception:
        vosk_words = []

    # Si Vosk detectó palabras en el audio
    if vosk_words and len(vosk_words) >= 1:
        # Extraer todas las palabras del guion/SRT
        all_script_words = []
        if srt_blocks:
            for b in srt_blocks:
                txt = b.get("display_text", b.get("raw_text", "")).strip()
                words = txt.split()
                all_script_words.extend(words)

        if not all_script_words:
            # Si no había texto en los bloques, usar directamente las palabras reconocidas por Vosk
            timed_words = [
                {"word": vw["word"], "start": float(vw["start"]), "end": float(vw["end"])}
                for vw in vosk_words
            ]
        else:
            # Alinear las palabras del usuario con las marcas acústicas de Vosk
            timed_words = align_words_to_vosk(all_script_words, vosk_words)

        # Agrupar en fragmentos de 2 a 3 palabras (o el tamaño configurado)
        step = max(1, max_words_per_chunk) if max_words_per_chunk > 0 else len(timed_words)
        aligned_chunks = []

        for i in range(0, len(timed_words), step):
            sub_chunk = timed_words[i:i + step]
            c_start = sub_chunk[0]["start"]
            c_end = sub_chunk[-1]["end"]
            
            # Suavizar pausas cortas entre palabras consecutivas
            c_dur = max(0.18, c_end - c_start)
            chunk_str = " ".join([item["word"] for item in sub_chunk])

            aligned_chunks.append({
                "index": f"vosk_{i // step + 1}",
                "start_time": c_start,
                "end_time": c_start + c_dur,
                "duration": c_dur,
                "display_text": chunk_str,
                "raw_text": chunk_str
            })

        if aligned_chunks:
            return aligned_chunks

    # Fallback: Alineación por envolvente de energía acústica (FFmpeg + RMS)
    return align_by_energy_envelope(srt_blocks, audio_path, max_words_per_chunk)

def extract_audio_samples(audio_path: str, start_sec: float = 0.0, duration: float = -1.0, sample_rate: int = 16000) -> Tuple[np.ndarray, int]:
    """Extrae muestras de audio en formato PCM float32 usando FFmpeg en memoria."""
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [ffmpeg_exe, "-y"]
    if start_sec > 0:
        cmd.extend(["-ss", f"{start_sec:.3f}"])
    if duration > 0:
        cmd.extend(["-t", f"{duration:.3f}"])
    cmd.extend(["-i", audio_path, "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"])
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    samples = np.frombuffer(proc.stdout, dtype=np.float32)
    return samples, sample_rate

def compute_energy_envelope(samples: np.ndarray, sample_rate: int = 16000, frame_ms: float = 25.0, hop_ms: float = 10.0) -> Tuple[np.ndarray, float]:
    """Calcula la curva de energía RMS y actividad vocal en ventanas deslizantes."""
    frame_size = int(sample_rate * (frame_ms / 1000.0))
    hop_size = int(sample_rate * (hop_ms / 1000.0))
    if len(samples) < frame_size:
        return np.ones(1, dtype=np.float32), 0.01

    num_frames = (len(samples) - frame_size) // hop_size + 1
    shape = (num_frames, frame_size)
    strides = (samples.strides[0] * hop_size, samples.strides[0])
    frames = np.lib.stride_tricks.as_strided(samples, shape=shape, strides=strides)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-8)
    kernel = np.ones(5) / 5.0
    smoothed_rms = np.convolve(rms, kernel, mode='same')
    return smoothed_rms, (hop_ms / 1000.0)

def align_by_energy_envelope(
    srt_blocks: List[Dict[str, Any]], 
    audio_path: str,
    max_words_per_chunk: int = 3
) -> List[Dict[str, Any]]:
    """
    Alinea los subtítulos a los picos de energía acústica y silencios del audio como respaldo.
    """
    if not srt_blocks:
        return []

    aligned = []
    for block in srt_blocks:
        start_sec = block.get("start_time", 0.0)
        end_sec = block.get("end_time", start_sec + 3.0)
        dur = max(0.1, end_sec - start_sec)
        raw_text = block.get("display_text", block.get("raw_text", "")).strip()
        words = raw_text.split()
        if not words:
            continue

        try:
            samples, sr = extract_audio_samples(audio_path, start_sec=start_sec, duration=dur)
            energy, step_t = compute_energy_envelope(samples, sr)
            thresh = np.min(energy) + 0.15 * (np.max(energy) - np.min(energy))
            active = np.where(energy > thresh)[0]
            v_start = active[0] * step_t if len(active) > 0 else 0.0
            v_end = min(dur, active[-1] * step_t + 0.1) if len(active) > 0 else dur
            v_span = max(0.2, v_end - v_start)

            weights = [max(1.0, len(re.sub(r'[^\w]', '', w))) for w in words]
            tot_w = sum(weights)
            curr = start_sec + v_start
            
            chunk_list = []
            step = max(1, max_words_per_chunk) if max_words_per_chunk > 0 else len(words)
            for i in range(0, len(words), step):
                c_words = words[i:i + step]
                c_weights = weights[i:i + step]
                c_dur = v_span * (sum(c_weights) / tot_w)
                chunk_list.append({
                    "text": " ".join(c_words),
                    "start": curr,
                    "end": curr + c_dur
                })
                curr += c_dur

            for idx, c in enumerate(chunk_list):
                aligned.append({
                    "index": f"{block.get('index', 1)}_{idx}",
                    "start_time": c["start"],
                    "end_time": c["end"],
                    "duration": max(0.1, c["end"] - c["start"]),
                    "display_text": c["text"],
                    "raw_text": c["text"]
                })
        except Exception:
            aligned.append(block)

    return aligned

# Alias de compatibilidad
def align_transcript_blocks_to_audio(
    srt_blocks: List[Dict[str, Any]], 
    audio_path: str,
    max_words_per_chunk: int = 3
) -> List[Dict[str, Any]]:
    return align_transcript_with_acoustic_analysis(srt_blocks, audio_path, max_words_per_chunk=max_words_per_chunk)
