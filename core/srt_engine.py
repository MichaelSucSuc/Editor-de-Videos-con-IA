import re
from typing import List, Dict, Any, Optional

def parse_srt_timestamp(time_str: str) -> float:
    """
    Convierte una marca de tiempo SRT 'HH:MM:SS,mmm' o 'HH:MM:SS.mmm' a segundos flotantes.
    """
    time_str = time_str.strip().replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        hours = float(parts[0])
        minutes = float(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        minutes = float(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds
    return float(parts[0])

def format_ass_timestamp(seconds: float) -> str:
    """
    Convierte segundos a formato de tiempo para subtítulos ASS: H:MM:SS.cc (centésimas de segundo).
    """
    if seconds < 0:
        seconds = 0
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = rem % 60
    centis = int(round((secs - int(secs)) * 100))
    if centis == 100:
        centis = 99
    return f"{hrs}:{mins:02d}:{int(secs):02d}.{centis:02d}"

def parse_srt(srt_content: str) -> List[Dict[str, Any]]:
    """
    Parsea subtítulos soportando dos formatos:
    1. Formato SRT estándar (con 00:00:00,000 --> 00:00:02,000)
    2. Formato simple con marcas de tiempo: [MM:SS] o [HH:MM:SS] Texto
    """
    blocks = []
    content = srt_content.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not content:
        return []

    # Detectar si es formato simple de corchetes [MM:SS] texto
    bracket_pattern = re.compile(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:[,\.]\d{1,3})?)\]\s*([^\n\[]+)', re.MULTILINE)
    bracket_matches = bracket_pattern.findall(content)

    if len(bracket_matches) >= 2:
        # Procesar formato [MM:SS] Frase
        raw_items = []
        for time_str, text_str in bracket_matches:
            time_sec = parse_srt_timestamp(time_str)
            clean_text = text_str.strip()
            if clean_text:
                raw_items.append((time_sec, clean_text))

        for idx in range(len(raw_items)):
            start_sec, clean_text = raw_items[idx]
            if idx + 1 < len(raw_items):
                end_sec = raw_items[idx + 1][0]
            else:
                end_sec = start_sec + 3.0  # Fallback para la última línea si no se ajusta con audio

            duration = max(0.1, end_sec - start_sec)
            
            explicit_img_match = re.search(r'\[(?:img:?\s*)?(\d+)\]', clean_text, re.IGNORECASE)
            explicit_img_num = int(explicit_img_match.group(1)) if explicit_img_match else None
            display_text = re.sub(r'\[(?:img:?\s*)?\d+\]', '', clean_text).strip()

            blocks.append({
                "index": idx + 1,
                "start_time": start_sec,
                "end_time": end_sec,
                "duration": duration,
                "raw_text": clean_text,
                "display_text": display_text,
                "explicit_img_number": explicit_img_num
            })
        return blocks

    # Si no es formato corchete, procesar como SRT estándar
    pattern = re.compile(
        r'(?:(\d+)\n)?'
        r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})[^\n]*\n'
        r'([\s\S]*?)(?=\n\s*\n\s*(?:\d+\n)?\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\Z)',
        re.MULTILINE
    )

    matches = pattern.findall(content)
    for idx, match in enumerate(matches, start=1):
        idx_str, start_raw, end_raw, text_raw = match
        start_sec = parse_srt_timestamp(start_raw)
        end_sec = parse_srt_timestamp(end_raw)
        duration = max(0.1, end_sec - start_sec)
        clean_text = text_raw.strip()

        explicit_img_match = re.search(r'\[(?:img:?\s*)?(\d+)\]', clean_text, re.IGNORECASE)
        explicit_img_num = int(explicit_img_match.group(1)) if explicit_img_match else None
        display_text = re.sub(r'\[(?:img:?\s*)?\d+\]', '', clean_text).strip()

        blocks.append({
            "index": int(idx_str) if idx_str and idx_str.isdigit() else idx,
            "start_time": start_sec,
            "end_time": end_sec,
            "duration": duration,
            "raw_text": clean_text,
            "display_text": display_text,
            "explicit_img_number": explicit_img_num
        })

    return blocks

def align_images_with_srt(
    images_metadata: List[Dict[str, Any]], 
    srt_blocks: List[Dict[str, Any]],
    total_audio_duration: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Calcula los intervalos de tiempo exactos (start_time, end_time, duration) para cada imagen.
    Garantiza que la duración total cubra desde 0.0s hasta el final del audio/SRT sin vacíos.
    """
    if not images_metadata:
        return []

    if not srt_blocks:
        # Si no hay SRT, repartir el tiempo total equitativamente entre las imágenes
        duration = total_audio_duration if total_audio_duration and total_audio_duration > 0 else (len(images_metadata) * 3.0)
        img_duration = duration / len(images_metadata)
        schedule = []
        for i, img in enumerate(images_metadata):
            start = i * img_duration
            end = start + img_duration
            schedule.append({
                "image": img,
                "start_time": start,
                "end_time": end,
                "duration": img_duration,
                "associated_texts": []
            })
        return schedule

    num_images = len(images_metadata)
    num_blocks = len(srt_blocks)
    
    total_end = srt_blocks[-1]["end_time"]
    if total_audio_duration and total_audio_duration > total_end:
        total_end = total_audio_duration

    # Estrategia 1: Comprobar si hay etiquetas explícitas [1], [2] en los bloques
    has_explicit_tags = any(b["explicit_img_number"] is not None for b in srt_blocks)
    
    schedule = []
    
    if has_explicit_tags:
        # Agrupar por etiqueta explícita
        img_by_num = {img["extracted_number"]: img for img in images_metadata}
        # Crear mapa de cortes según etiquetas
        cuts = []
        current_img = images_metadata[0]
        for b in srt_blocks:
            if b["explicit_img_number"] is not None and b["explicit_img_number"] in img_by_num:
                current_img = img_by_num[b["explicit_img_number"]]
            cuts.append((b, current_img))
            
        # Unir bloques consecutivos con la misma imagen
        current_entry = None
        for block, img in cuts:
            if current_entry is None or current_entry["image"]["absolute_path"] != img["absolute_path"]:
                if current_entry:
                    schedule.append(current_entry)
                current_entry = {
                    "image": img,
                    "start_time": block["start_time"],
                    "end_time": block["end_time"],
                    "duration": block["duration"],
                    "associated_texts": [block["display_text"]]
                }
            else:
                current_entry["end_time"] = block["end_time"]
                current_entry["duration"] = current_entry["end_time"] - current_entry["start_time"]
                current_entry["associated_texts"].append(block["display_text"])
        if current_entry:
            schedule.append(current_entry)

    elif num_images == num_blocks:
        # Caso 1 a 1 directo: cada imagen con su bloque respectivo
        prev_end = 0.0
        for i, (img, block) in enumerate(zip(images_metadata, srt_blocks)):
            # La primera imagen arranca en 0.0s para no dejar pantalla negra antes de hablar
            start = 0.0 if i == 0 else block["start_time"]
            # Cada imagen cubre hasta el inicio de la siguiente para que no haya huecos negros en silencios
            next_start = srt_blocks[i + 1]["start_time"] if i + 1 < num_blocks else total_end
            end = next_start
            schedule.append({
                "image": img,
                "start_time": start,
                "end_time": end,
                "duration": max(0.1, end - start),
                "associated_texts": [block["display_text"]]
            })

    elif num_images < num_blocks:
        # Hay más bloques de texto que imágenes: repartir los bloques en grupos entre las imágenes
        blocks_per_img = num_blocks / num_images
        for i, img in enumerate(images_metadata):
            start_block_idx = int(round(i * blocks_per_img))
            end_block_idx = int(round((i + 1) * blocks_per_img)) - 1
            start_block_idx = min(start_block_idx, num_blocks - 1)
            end_block_idx = min(max(end_block_idx, start_block_idx), num_blocks - 1)

            first_block = srt_blocks[start_block_idx]
            last_block = srt_blocks[end_block_idx]

            start = 0.0 if i == 0 else first_block["start_time"]
            if i + 1 < num_images:
                next_first_block = srt_blocks[min(int(round((i + 1) * blocks_per_img)), num_blocks - 1)]
                end = next_first_block["start_time"]
            else:
                end = total_end

            texts = [b["display_text"] for b in srt_blocks[start_block_idx : end_block_idx + 1]]

            schedule.append({
                "image": img,
                "start_time": start,
                "end_time": end,
                "duration": max(0.1, end - start),
                "associated_texts": texts
            })

    else:
        # Hay más imágenes que bloques de texto: repartir el tiempo total de manera proporcional
        img_duration = total_end / num_images
        for i, img in enumerate(images_metadata):
            start = i * img_duration
            end = total_end if i == num_images - 1 else (i + 1) * img_duration
            # Asociar los textos que caigan dentro de esta ventana
            matching_texts = [
                b["display_text"] for b in srt_blocks 
                if (b["start_time"] >= start and b["start_time"] < end) or
                   (b["end_time"] > start and b["end_time"] <= end)
            ]
            schedule.append({
                "image": img,
                "start_time": start,
                "end_time": end,
                "duration": max(0.1, end - start),
                "associated_texts": matching_texts
            })

    # Asegurar que el primer elemento empiece en 0.0 y el último termine en total_end
    if schedule:
        schedule[0]["start_time"] = 0.0
        schedule[0]["duration"] = schedule[0]["end_time"] - schedule[0]["start_time"]
        schedule[-1]["end_time"] = total_end
        schedule[-1]["duration"] = schedule[-1]["end_time"] - schedule[-1]["start_time"]

    return schedule
