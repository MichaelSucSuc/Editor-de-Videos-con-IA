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
    Prioriza la carpeta local 'models/' dentro del proyecto para que la aplicación
    sea 100% portable y autónoma en cualquier computadora sin internet.
    """
    global _GLOBAL_VOSK_MODEL
    if _GLOBAL_VOSK_MODEL is None:
        import vosk
        vosk.SetLogLevel(-1)

        # Buscar en carpetas locales del proyecto (modo portable / pendrive)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate_paths = [
            os.path.join(base_dir, "models", "vosk-model-small-es-0.42"),
            os.path.join(base_dir, "models", "vosk-es"),
            os.path.join(base_dir, "models")
        ]

        for cand in candidate_paths:
            if os.path.exists(cand) and (os.path.exists(os.path.join(cand, "am")) or os.path.exists(os.path.join(cand, "conf"))):
                _GLOBAL_VOSK_MODEL = vosk.Model(cand)
                return _GLOBAL_VOSK_MODEL

        # Fallback a caché del sistema o descarga automática si no está en models/
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

def count_phonetic_weight(text: str) -> float:
    """
    Calcula el peso fonético de un texto en español basado en núcleos vocálicos
    y consonantes para modelar la duración hablada real con precisión.
    """
    clean = re.sub(r'[^\w\s]', '', text).lower()
    vowels = len(re.findall(r'[aeiouáéíóúü]', clean))
    chars = len(clean.replace(' ', ''))
    return max(1.0, vowels * 1.35 + chars * 0.25)

def detect_voice_activity_bounds(audio_path: str, start_sec: float, duration: float) -> Tuple[float, float]:
    """
    Analiza la envolvente de energía acústica RMS en la ventana [start_sec, start_sec + duration]
    para detectar cuándo comienza a hablar el locutor y cuándo se detiene antes del corte.
    """
    try:
        samples, sr = extract_audio_samples(audio_path, start_sec=start_sec, duration=duration)
        if len(samples) < sr * 0.1:
            return start_sec + 0.05, start_sec + max(0.2, duration - 0.06)

        energy, step_t = compute_energy_envelope(samples, sr)
        e_min = float(np.min(energy))
        e_max = float(np.max(energy))
        e_range = e_max - e_min

        if e_range < 1e-4:
            return start_sec + 0.05, start_sec + max(0.2, duration - 0.06)

        thresh = e_min + 0.12 * e_range
        active = np.where(energy > thresh)[0]

        if len(active) == 0:
            return start_sec + 0.05, start_sec + max(0.2, duration - 0.06)

        v_start_offset = active[0] * step_t
        v_end_offset = min(duration, active[-1] * step_t + 0.10)

        actual_start = start_sec + max(0.0, v_start_offset)
        actual_end = start_sec + min(duration - 0.04, v_end_offset)

        if actual_end <= actual_start + 0.2:
            actual_end = actual_start + max(0.3, duration * 0.88)

        return actual_start, actual_end
    except Exception:
        return start_sec + 0.05, start_sec + max(0.2, duration - 0.06)

def align_transcript_with_acoustic_analysis(
    srt_blocks: List[Dict[str, Any]],
    audio_path: str,
    max_words_per_chunk: int = 3
) -> List[Dict[str, Any]]:
    """
    Sincronización híbrida perfecta:
    1. Las marcas [MM:SS] del usuario definen los cortes de imagen.
    2. El texto del usuario proporciona las palabras exactas, puntuación y gramática.
    3. El audio proporciona la detección acústica real (inicio de voz, pausas y fin).
    4. Cada frase se subdivide en fragmentos cortos de 2-3 palabras ponderados por fonética silábica.
    5. Se aplica una separación limpia (GAP de 45ms) entre subtítulos para que NUNCA se solapen visualmente.
    """
    if not os.path.exists(audio_path) or not srt_blocks:
        return srt_blocks

    try:
        vosk_words = extract_vosk_word_timestamps(audio_path)
    except Exception:
        vosk_words = []

    aligned_chunks = []
    ANTI_OVERLAP_GAP = 0.045  # 45 ms de silencio visual para transición nítida e instantánea

    for b_idx, block in enumerate(srt_blocks):
        b_start = float(block.get("start_time", 0.0))
        b_end = float(block.get("end_time", b_start + 3.0))
        b_dur = max(0.2, b_end - b_start)
        b_text = block.get("display_text", block.get("raw_text", "")).strip()
        words = b_text.split()
        if not words:
            continue

        # 1. Detectar inicio y fin real de la voz en este bloque mediante energía RMS
        v_start, v_end = detect_voice_activity_bounds(audio_path, b_start, b_dur)
        v_span = max(0.3, v_end - v_start)

        # 2. Dividir la frase en fragmentos dinámicos de 2 a 3 palabras
        step = max(1, max_words_per_chunk) if max_words_per_chunk > 0 else len(words)
        chunk_texts = [" ".join(words[i:i + step]) for i in range(0, len(words), step)]
        
        # 3. Ponderación fonética proporcional a la longitud hablada real
        weights = [count_phonetic_weight(txt) for txt in chunk_texts]
        tot_weight = sum(weights)

        # 4. Palabras reconocidas por Vosk en este intervalo para ajuste fino
        block_vosk = [
            w for w in vosk_words 
            if (float(w["start"]) >= b_start - 0.35 and float(w["end"]) <= b_end + 0.35)
        ]

        # 5. Distribuir temporalmente los fragmentos
        block_chunks = []
        curr_t = v_start

        for i, (ctxt, w_val) in enumerate(zip(chunk_texts, weights)):
            c_dur = v_span * (w_val / tot_weight)
            c_start = curr_t
            c_end = curr_t + c_dur

            # Si Vosk detectó la primera palabra de este fragmento, ajustar inicio a la voz real
            if block_vosk:
                first_norm = normalize_word(ctxt.split()[0])
                for vw in block_vosk:
                    if normalize_word(vw["word"]) == first_norm:
                        if abs(float(vw["start"]) - c_start) < 0.6:
                            c_start = max(b_start, float(vw["start"]))
                            c_end = max(c_start + 0.2, c_end)
                        break

            block_chunks.append({
                "index": f"{block.get('index', b_idx + 1)}_{i + 1}",
                "start_time": c_start,
                "end_time": c_end,
                "duration": max(0.15, c_end - c_start),
                "display_text": ctxt,
                "raw_text": ctxt
            })
            curr_t = c_end

        # 6. CRÍTICO: Eliminar cualquier solapamiento visual entre fragmentos consecutivos
        for i in range(len(block_chunks) - 1):
            next_start = block_chunks[i + 1]["start_time"]
            if block_chunks[i]["end_time"] >= next_start - ANTI_OVERLAP_GAP:
                block_chunks[i]["end_time"] = max(block_chunks[i]["start_time"] + 0.12, next_start - ANTI_OVERLAP_GAP)
            block_chunks[i]["duration"] = block_chunks[i]["end_time"] - block_chunks[i]["start_time"]

        # Asegurar que el último fragmento de la imagen termine limpiamente antes del corte
        if block_chunks:
            block_chunks[-1]["end_time"] = min(b_end - ANTI_OVERLAP_GAP, block_chunks[-1]["end_time"])
            block_chunks[-1]["duration"] = max(0.12, block_chunks[-1]["end_time"] - block_chunks[-1]["start_time"])

        aligned_chunks.extend(block_chunks)

    # 7. FILTRO GLOBAL: Garantizar separación limpia absoluta entre TODOS los subtítulos consecutivos del video
    # (Evita que un subtítulo aparezca mientras el anterior está desapareciendo)
    for i in range(len(aligned_chunks) - 1):
        c1 = aligned_chunks[i]
        c2 = aligned_chunks[i + 1]
        if c1["end_time"] >= c2["start_time"] - ANTI_OVERLAP_GAP:
            c1["end_time"] = max(c1["start_time"] + 0.12, c2["start_time"] - ANTI_OVERLAP_GAP)
            c1["duration"] = max(0.10, c1["end_time"] - c1["start_time"])

    return aligned_chunks

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
