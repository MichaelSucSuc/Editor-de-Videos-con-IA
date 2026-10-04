import os
from typing import List, Dict, Any
from core.srt_engine import format_ass_timestamp

SUBTITLE_STYLES = {
    "hormozi": {
        "name": "Alex Hormozi (Amarillo Neón & Alto Impacto)",
        "fontname": "Arial Black",
        "fontsize": 88,                  # Aumentado para máximo impacto visual
        "primary_color": "&H0000FFFF&",  # Amarillo neón en formato BGR de ASS
        "outline_color": "&H00000000&",  # Negro sólido grueso
        "back_color": "&H80000000&",
        "bold": 1,
        "outline": 6,
        "shadow": 4,
        "alignment": 2,                  # Centrado horizontalmente
        "margin_v_ratio": 0.28,          # 28% de la altura de la pantalla (sube para evitar zona de botones de TikTok)
        "uppercase": True,
        "animation_tag": r"{\t(0,90,\fscx118\fscy118)\t(90,180,\fscx100\fscy100)}"
    },
    "mrbeast": {
        "name": "MrBeast (Cómic Inclinado & Dinámico)",
        "fontname": "Impact",
        "fontsize": 94,
        "primary_color": "&H00FFFFFF&",  # Blanco brillante
        "outline_color": "&H00000000&",  # Borde negro ultra marcado
        "back_color": "&H000000FF&",     # Rojo
        "bold": 1,
        "outline": 7,
        "shadow": 5,
        "alignment": 2,
        "margin_v_ratio": 0.28,
        "uppercase": True,
        "animation_tag": r"{\frz-3\t(0,100,\fscx115\fscy115)\t(100,200,\fscx100\fscy100)}"
    },
    "vox": {
        "name": "Vox / Documental Cinemático (Elegante & Clean)",
        "fontname": "Segoe UI",
        "fontsize": 64,
        "primary_color": "&H00F0F0F0&",  # Blanco suave
        "outline_color": "&H00000000&",
        "back_color": "&HA0000000&",     # Caja negra translúcida
        "bold": 1,
        "outline": 0,
        "shadow": 0,
        "border_style": 3,               # Fondo estilo caja (box)
        "alignment": 2,
        "margin_v_ratio": 0.26,
        "uppercase": False,
        "animation_tag": r"{\fad(40,0)}"
    },
    "neon_glow": {
        "name": "Neon Glow (Cyberpunk Cyan & Resplandor)",
        "fontname": "Arial Black",
        "fontsize": 84,
        "primary_color": "&H00FFFF00&",  # Cyan eléctrico (BGR)
        "outline_color": "&H00FF007F&",  # Borde Magenta resplandeciente
        "back_color": "&H00000000&",
        "bold": 1,
        "outline": 5,
        "shadow": 3,
        "alignment": 2,
        "margin_v_ratio": 0.28,
        "uppercase": True,
        "animation_tag": r"{\blur4\t(0,100,\fscx115\fscy115)\t(100,200,\fscx100\fscy100)}"
    },
    "minimal": {
        "name": "Minimalista Clásico (Blanco con Sombra)",
        "fontname": "Segoe UI",
        "fontsize": 72,
        "primary_color": "&H00FFFFFF&",
        "outline_color": "&H00000000&",
        "back_color": "&H80000000&",
        "bold": 1,
        "outline": 3,
        "shadow": 3,
        "alignment": 2,
        "margin_v_ratio": 0.25,
        "uppercase": False,
        "animation_tag": ""
    }
}

def chunk_srt_block(block: Dict[str, Any], max_words: int = 3) -> List[Dict[str, Any]]:
    """
    Divide un bloque de subtítulo largo en sub-bloques cortos de 2 a 3 palabras
    distribuyendo el tiempo proporcionalmente para dar dinamismo constante y palabras grandes.
    """
    if max_words <= 0:
        return [block]

    raw_text = block.get("display_text", block.get("raw_text", "")).strip()
    words = raw_text.split()
    if len(words) <= max_words:
        return [block]

    # Agrupar palabras en trozos de tamaño max_words
    chunks = []
    for i in range(0, len(words), max_words):
        chunk_words = words[i:i + max_words]
        chunks.append(" ".join(chunk_words))

    total_duration = block.get("duration", 3.0)
    start_time = block.get("start_time", 0.0)
    time_per_chunk = total_duration / float(len(chunks))

    sub_blocks = []
    for idx, chunk_text in enumerate(chunks):
        c_start = start_time + idx * time_per_chunk
        c_end = start_time + (idx + 1) * time_per_chunk
        sub_blocks.append({
            "index": f"{block.get('index', 1)}_{idx}",
            "start_time": c_start,
            "end_time": c_end,
            "duration": time_per_chunk,
            "display_text": chunk_text,
            "raw_text": chunk_text
        })

    return sub_blocks

from core.voice_aligner import align_transcript_blocks_to_audio

def generate_ass_file(
    srt_blocks: List[Dict[str, Any]], 
    output_ass_path: str,
    style_key: str = "hormozi",
    video_width: int = 1080,
    video_height: int = 1920,
    max_words_per_subtitle: int = 3,
    position_mode: str = "safe_tiktok",
    audio_path: str = None
) -> str:
    """
    Convierte una lista de bloques SRT en un archivo de subtítulos .ass avanzado:
    1. Si se proporciona audio, analiza internamente la voz (energía y pausas) para marcas de tiempo acústicamente exactas.
    2. Subdivide frases largas en ráfagas de 2-3 palabras para dinamismo viral continuo.
    3. Coloca los subtítulos en una posición elevada óptima (lejos de la barra inferior de TikTok).
    4. Aplica tipografía de gran tamaño con animación de impacto (bounce/pop).
    """
    style = SUBTITLE_STYLES.get(style_key, SUBTITLE_STYLES["hormozi"])
    border_style = style.get("border_style", 1)

    # Calcular posición vertical (MarginV)
    if position_mode == "center":
        alignment = 5
        margin_v = 0
    elif position_mode == "bottom_low":
        alignment = 2
        margin_v = int(video_height * 0.10)
    else:  # "safe_tiktok" (Recomendado)
        alignment = 2
        ratio = style.get("margin_v_ratio", 0.28)
        margin_v = int(video_height * ratio)

    # Escalar tamaño de fuente si el video es horizontal (1080p estándar)
    base_fontsize = style['fontsize']
    if video_height < 1400:
        fontsize = int(base_fontsize * (video_height / 1920.0) * 1.2)
    else:
        fontsize = base_fontsize

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['fontname']},{fontsize},{style['primary_color']},&H000000FF&,{style['outline_color']},{style['back_color']},{style['bold']},0,0,0,100,100,0,0,{border_style},{style['outline']},{style['shadow']},{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Si se pasa audio, analizar acústicamente la voz para sincronizar cada palabra con precisión de milisegundos
    if audio_path and os.path.exists(audio_path):
        expanded_blocks = align_transcript_blocks_to_audio(srt_blocks, audio_path, max_words_per_chunk=max_words_per_subtitle)
    else:
        expanded_blocks = []
        for block in srt_blocks:
            if block.get("_already_chunked"):
                expanded_blocks.append(block)
            else:
                sub_list = chunk_srt_block(block, max_words=max_words_per_subtitle)
                expanded_blocks.extend(sub_list)

    # Garantizar separación limpia absoluta (GAP de 90ms = 3 fotogramas) para evitar que un subtítulo
    # aparezca mientras el anterior está desapareciendo (cero solapamiento visual)
    GAP = 0.090
    for i in range(len(expanded_blocks) - 1):
        curr_b = expanded_blocks[i]
        next_b = expanded_blocks[i + 1]
        if curr_b["end_time"] >= next_b["start_time"] - GAP:
            curr_b["end_time"] = max(curr_b["start_time"] + 0.12, next_b["start_time"] - GAP)
            curr_b["duration"] = max(0.10, curr_b["end_time"] - curr_b["start_time"])

    events = []
    anim = style.get("animation_tag", "")

    for b in expanded_blocks:
        start_ass = format_ass_timestamp(b["start_time"])
        end_ass = format_ass_timestamp(b["end_time"])

        text = b.get("display_text", b.get("raw_text", "")).strip()
        if style.get("uppercase", False):
            text = text.upper()

        text = text.replace('\n', r'\N')
        line_content = f"{anim}{text}" if anim else text
        event_line = f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{line_content}"
        events.append(event_line)

    full_ass_content = header + "\n".join(events) + "\n"

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(full_ass_content)

    return output_ass_path
