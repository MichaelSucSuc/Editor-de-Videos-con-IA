from typing import List, Dict, Any

MOTION_TYPES = [
    "zoom_in",
    "zoom_out",
    "pan_left_to_right",
    "pan_right_to_left",
    "corner_zoom"
]

def build_clip_filter(
    motion_type: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30
) -> str:
    """
    Genera la cadena de filtro de video FFmpeg para aplicar escala, relación de aspecto
    y movimiento de cámara dinámico (Ken Burns) durante la duración exacta especificada.
    """
    total_frames = max(1, int(round(duration * fps)))
    
    # 1. Pre-escalar la imagen con recorte centrado para que encaje perfectamente en la resolución destino sin barras negras
    # scale=-2:2560 o scale=2560:-2 mantiene alta resolución para que el zoom no pixelee
    upscale_w = int(width * 1.3)
    upscale_h = int(height * 1.3)
    
    # Expresión de zoompan según el movimiento seleccionado
    # on = output frame number (0 to total_frames)
    if motion_type == "zoom_in":
        # Zoom suave de 1.0 a 1.20 centrado
        step = 0.20 / total_frames
        zoom_expr = f"min(1.0+{step:.6f}*on,1.25)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    elif motion_type == "zoom_out":
        # Zoom out suave de 1.20 a 1.0 centrado
        step = 0.20 / total_frames
        zoom_expr = f"max(1.20-{step:.6f}*on,1.0)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    elif motion_type == "pan_left_to_right":
        # Zoom fijo al 1.15 y paneo horizontal de izquierda a derecha
        zoom_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
        y_expr = "ih/2-(ih/zoom/2)"

    elif motion_type == "pan_right_to_left":
        # Zoom fijo al 1.15 y paneo horizontal de derecha a izquierda
        zoom_expr = "1.15"
        x_expr = f"(iw-iw/zoom)*(1-(on/{total_frames}))"
        y_expr = "ih/2-(ih/zoom/2)"

    elif motion_type == "corner_zoom":
        # Zoom suave enfocando tercio superior (ideal para rostros/sujetos)
        step = 0.22 / total_frames
        zoom_expr = f"min(1.0+{step:.6f}*on,1.25)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/3-(ih/zoom/3)"

    else:
        # Estático o fallback
        zoom_expr = "1.0"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    filter_chain = (
        f"scale={upscale_w}:{upscale_h}:force_original_aspect_ratio=increase,"
        f"crop={upscale_w}:{upscale_h},"
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={total_frames}:s={width}x{height}:fps={fps},"
        f"trim=duration={duration:.3f},"
        f"setsar=1"
    )

    return filter_chain

def assign_motions_to_schedule(
    schedule: List[Dict[str, Any]], 
    motion_mode: str = "dynamic"
) -> List[Dict[str, Any]]:
    """
    Asigna un tipo de movimiento a cada segmento de imagen.
    En modo 'dynamic', alterna de forma inteligente para que nunca se repita el mismo movimiento.
    """
    for i, item in enumerate(schedule):
        if motion_mode == "dynamic":
            item["motion_type"] = MOTION_TYPES[i % len(MOTION_TYPES)]
        elif motion_mode in MOTION_TYPES:
            item["motion_type"] = motion_mode
        else:
            item["motion_type"] = "zoom_in"
    return schedule
