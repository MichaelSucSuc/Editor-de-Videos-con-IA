from typing import List, Dict, Any

TRANSITION_TYPES = {
    "none": "Corte Directo (Sin transición)",
    "fade": "Disolución Suave (Crossfade)",
    "wipeleft": "Barrido a la Izquierda (Wipe Left)",
    "wiperight": "Barrido a la Derecha (Wipe Right)",
    "slideleft": "Desplazamiento Lateral (Slide Left)",
    "slideright": "Desplazamiento Lateral (Slide Right)",
    "circlecrop": "Círculo Iris (Circle Crop)",
    "zoomin": "Zoom In Transición",
    "radial": "Barrido Radial Reloj"
}

def calculate_transition_plan(
    schedule: List[Dict[str, Any]], 
    transition_type: str = "fade",
    transition_duration: float = 0.35
) -> Dict[str, Any]:
    """
    Calcula los offsets y extensiones de tiempo de cada clip para que las transiciones
    ocurran exactamente sobre el punto de corte del SRT sin 'comerse' tiempo ni
    desincronizar el audio ni los subtítulos.
    
    Regla de oro: Si el clip i debe cambiar en T, la transición ocurre entre T - (dur/2) y T + (dur/2).
    Cada clip se alarga (dur/2) para compensar la superposición exacta de xfade.
    """
    n = len(schedule)
    if n <= 1 or transition_type == "none":
        return {
            "has_transitions": False,
            "transition_type": "none",
            "transition_duration": 0.0,
            "clips": schedule
        }

    half_trans = transition_duration / 2.0
    clips_plan = []
    
    for i, item in enumerate(schedule):
        base_dur = item["duration"]
        # El primer clip solo se extiende al final
        # El último clip solo se extiende al inicio
        # Los clips intermedios se extienden al inicio y al final
        pad_start = half_trans if i > 0 else 0.0
        pad_end = half_trans if i < (n - 1) else 0.0
        
        extended_duration = base_dur + pad_start + pad_end
        
        clips_plan.append({
            "original_index": i,
            "image": item["image"],
            "motion_type": item.get("motion_type", "zoom_in"),
            "base_start": item["start_time"],
            "base_end": item["end_time"],
            "base_duration": base_dur,
            "pad_start": pad_start,
            "pad_end": pad_end,
            "render_duration": extended_duration,
            "associated_texts": item.get("associated_texts", [])
        })

    # Calcular los offsets para el filtro xfade de FFmpeg
    # Cada xfade consume 'transition_duration'
    # El offset acumulado coincide exactamente con el momento del corte
    cumulative_time = 0.0
    xfade_offsets = []
    for i in range(n - 1):
        cumulative_time += schedule[i]["duration"]
        # El offset en xfade es el tiempo transcurrido desde el inicio menos la mitad de la transición
        xfade_offsets.append(cumulative_time - half_trans)

    return {
        "has_transitions": True,
        "transition_type": transition_type,
        "transition_duration": transition_duration,
        "clips": clips_plan,
        "offsets": xfade_offsets
    }
