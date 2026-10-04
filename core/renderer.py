import os
import sys
import shutil
import tempfile
import subprocess
from typing import List, Dict, Any, Callable, Optional

import imageio_ffmpeg
from core.ffmpeg_utils import get_ffmpeg_path
from core.motion_engine import build_clip_filter
from core.transitions import calculate_transition_plan
from core.parallax_3d import generate_3d_parallax_clip

def get_audio_duration(audio_path: str) -> float:
    """
    Obtiene la duración en segundos de un archivo de audio mediante ffprobe/ffmpeg.
    """
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [
        ffmpeg_exe,
        "-i", audio_path,
        "-f", "null",
        "-"
    ]
    # Ejecutar para leer la duración en stderr
    proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")
    import re
    match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", proc.stderr)
    if match:
        h, m, s = match.groups()
        return float(h) * 3600 + float(m) * 60 + float(s)
    return 0.0

def render_video_pipeline(
    schedule: List[Dict[str, Any]],
    audio_path: str,
    output_path: str,
    subtitle_ass_path: Optional[str] = None,
    aspect_ratio: str = "9:16",
    transition_type: str = "fade",
    transition_duration: float = 0.35,
    enable_3d_parallax: bool = False,
    fps: int = 30,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Orquesta el pipeline completo de renderizado:
    1. Calcula plan de transiciones y extensiones de clips.
    2. Renderiza cada clip individual (con efecto 3D Parallax o Ken Burns) en una carpeta temporal.
    3. Concatena los clips con o sin transiciones xfade.
    4. Quema los subtítulos estilizados (.ass) y mezcla el audio.
    5. Exporta el archivo MP4 definitivo de alta calidad.
    """
    ffmpeg_exe = get_ffmpeg_path()
    
    if aspect_ratio == "16:9":
        width, height = 1920, 1080
    else:  # "9:16" Vertical por defecto
        width, height = 1080, 1920

    # Crear directorio temporal para fragmentos
    temp_dir = tempfile.mkdtemp(prefix="editor_ia_")
    
    try:
        def update_progress(pct: float, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        update_progress(5.0, "Preparando clips y plan de movimiento...")
        
        # 1. Calcular plan de transiciones
        plan = calculate_transition_plan(schedule, transition_type, transition_duration)
        clips_info = plan["clips"]
        total_clips = len(clips_info)
        
        rendered_clip_files = []
        
        # 2. Renderizar cada clip individual con su zoompan o 3D Parallax
        for idx, clip in enumerate(clips_info, start=1):
            clip_dur = clip.get("render_duration", clip.get("duration", 3.0))
            motion = clip.get("motion_type", "zoom_in")
            img_path = clip["image"]["absolute_path"]
            
            clip_filename = os.path.join(temp_dir, f"clip_{idx:03d}.mp4")

            # Determinar si es video o imagen fija
            is_video = clip["image"].get("media_type") == "video"
            if not is_video:
                ext = os.path.splitext(img_path)[1].lower()
                is_video = ext in {'.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'}

            if is_video:
                update_progress(
                    5.0 + (idx / total_clips) * 45.0, 
                    f"Procesando clip de video {idx} de {total_clips} (repetición en bucle si es corto)..."
                )
                # Escalar, centrar y forzar fps al video
                vf_video = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"setsar=1,"
                    f"fps={fps}"
                )
                # -stream_loop -1 repite en bucle el video tantas veces como sea necesario
                # -t corta exactamente en la duración requerida por el guion
                # -an remueve el audio original del video para escuchar solo la voz
                cmd_clip = [
                    ffmpeg_exe,
                    "-y",
                    "-stream_loop", "-1",
                    "-i", img_path,
                    "-t", f"{clip_dur:.3f}",
                    "-vf", vf_video,
                    "-an",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "veryfast",
                    "-r", str(fps),
                    clip_filename
                ]
                proc = subprocess.run(cmd_clip, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
                if proc.returncode != 0:
                    raise RuntimeError(f"Error procesando video {idx} ({os.path.basename(img_path)}): {proc.stderr}")

            elif enable_3d_parallax:
                update_progress(
                    5.0 + (idx / total_clips) * 45.0, 
                    f"Generando profundidad 3D Parallax en imagen {idx} de {total_clips}..."
                )
                generate_3d_parallax_clip(
                    image_path=img_path,
                    output_clip_path=clip_filename,
                    duration=clip_dur,
                    width=width,
                    height=height,
                    fps=fps
                )
            else:
                filter_str = build_clip_filter(
                    motion_type=motion,
                    duration=clip_dur,
                    width=width,
                    height=height,
                    fps=fps
                )
                
                cmd_clip = [
                    ffmpeg_exe,
                    "-y",
                    "-loop", "1",
                    "-i", img_path,
                    "-vf", filter_str,
                    "-t", f"{clip_dur:.3f}",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    "-preset", "veryfast",
                    "-r", str(fps),
                    clip_filename
                ]
                
                update_progress(
                    5.0 + (idx / total_clips) * 45.0, 
                    f"Procesando animación de imagen {idx} de {total_clips} ({motion})..."
                )
                
                proc = subprocess.run(cmd_clip, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
                if proc.returncode != 0:
                    raise RuntimeError(f"Error renderizando clip {idx}: {proc.stderr}")
                
            rendered_clip_files.append(clip_filename)

        update_progress(55.0, "Ensamblando secuencia de video...")
        
        # 3. Concatenación / Transición
        merged_video_path = os.path.join(temp_dir, "merged.mp4")
        
        if not plan["has_transitions"] or total_clips <= 1:
            # Concat simple mediante archivo de lista
            concat_list_path = os.path.join(temp_dir, "concat_list.txt")
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for c_file in rendered_clip_files:
                    # Normalizar ruta para FFmpeg
                    clean_path = os.path.abspath(c_file).replace('\\', '/')
                    f.write(f"file '{clean_path}'\n")
                    
            cmd_concat = [
                ffmpeg_exe,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-c", "copy",
                merged_video_path
            ]
            proc = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
            if proc.returncode != 0:
                raise RuntimeError(f"Error al concatenar clips: {proc.stderr}")
        else:
            # Concat con xfade
            # Construir filtro xfade en cadena
            inputs = []
            for c_file in rendered_clip_files:
                inputs.extend(["-i", c_file])
                
            trans_name = plan["transition_type"]
            trans_dur = plan["transition_duration"]
            offsets = plan["offsets"]
            
            filter_parts = []
            last_out = "[0:v]"
            for i in range(total_clips - 1):
                next_in = f"[{i+1}:v]"
                out_label = f"[v{i+1}]" if i < (total_clips - 2) else "[vout]"
                offset = offsets[i]
                filter_parts.append(
                    f"{last_out}{next_in}xfade=transition={trans_name}:duration={trans_dur:.3f}:offset={offset:.3f}{out_label}"
                )
                last_out = out_label
                
            filter_complex = ";".join(filter_parts)
            
            cmd_xfade = [
                ffmpeg_exe,
                "-y",
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                merged_video_path
            ]
            
            update_progress(65.0, "Aplicando transiciones sin desfase de audio...")
            proc = subprocess.run(cmd_xfade, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
            if proc.returncode != 0:
                # Si falla xfade (ej. nombre no compatible), fallback a concat suave
                concat_list_path = os.path.join(temp_dir, "concat_list.txt")
                with open(concat_list_path, "w", encoding="utf-8") as f:
                    for c_file in rendered_clip_files:
                        clean_path = os.path.abspath(c_file).replace('\\', '/')
                        f.write(f"file '{clean_path}'\n")
                cmd_concat = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", merged_video_path]
                subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        update_progress(80.0, "Incrustando audio y subtítulos estilizados...")
        
        # 4. Final: Unir video con audio y quemar subtítulos ASS
        final_vf_filters = []
        if subtitle_ass_path and os.path.exists(subtitle_ass_path):
            safe_ass = os.path.join(temp_dir, "safe_subs.ass")
            shutil.copy2(subtitle_ass_path, safe_ass)
            escaped_ass = os.path.abspath(safe_ass).replace('\\', '/').replace(':', r'\:')
            final_vf_filters.append(f"subtitles='{escaped_ass}'")
            
        vf_arg = []
        if final_vf_filters:
            vf_arg = ["-vf", ",".join(final_vf_filters)]
            
        cmd_final = [
            ffmpeg_exe,
            "-y",
            "-i", merged_video_path,
            "-i", audio_path,
            *vf_arg,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",  # Alta calidad visual
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",  # Ajustar a la duración exacta del audio/video
            output_path
        ]
        
        update_progress(90.0, "Renderizando video final en alta definición...")
        proc = subprocess.run(cmd_final, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
        if proc.returncode != 0:
            raise RuntimeError(f"Error en render final: {proc.stderr}")

        update_progress(100.0, "¡Video finalizado exitosamente!")
        return output_path

    finally:
        # Limpiar carpeta temporal
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
