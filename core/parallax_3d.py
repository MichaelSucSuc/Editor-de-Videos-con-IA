import os
import cv2
import numpy as np
import subprocess
from core.ffmpeg_utils import get_ffmpeg_path

def estimate_salience_depth_map(img_rgb: np.ndarray) -> np.ndarray:
    """
    Calcula un mapa de profundidad focal basado en prominencia del sujeto (Saliency + Edge Guided Depth).
    El sujeto principal (cercano al centro o con alto contraste) obtiene valor cercano a 1.0 (primer plano),
    mientras que el fondo obtiene valores cercanos a 0.0 (plano alejado).
    """
    h, w = img_rgb.shape[:2]
    
    # 1. Gradiente radial centrado con elipse vertical (típico para sujetos/retratos)
    y_indices, x_indices = np.indices((h, w))
    center_x, center_y = w / 2.0, h * 0.45  # Ligeramente arriba del centro (rostros/cuerpos)
    
    # Normalizar distancias
    norm_x = (x_indices - center_x) / (w * 0.55)
    norm_y = (y_indices - center_y) / (h * 0.55)
    dist_sq = norm_x**2 + norm_y**2
    radial_depth = np.exp(-dist_sq * 1.5)
    
    # 2. Refinamiento con luminancia y bordes para adaptarse a las formas de la imagen
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (21, 21), 0)
    norm_gray = blurred.astype(np.float32) / 255.0
    
    # Combinar mapa radial con detalles de la imagen
    depth = 0.7 * radial_depth + 0.3 * norm_gray
    depth = cv2.GaussianBlur(depth, (31, 31), 0)
    
    # Normalizar entre 0.0 (fondo) y 1.0 (primer plano)
    depth = (depth - depth.min()) / (depth.max() - depth.min() + 1e-6)
    return depth.astype(np.float32)

def generate_3d_parallax_clip(
    image_path: str,
    output_clip_path: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    direction: str = "push_in"
) -> str:
    """
    Toma una imagen fija y genera un video en formato MP4 con animación de cámara 3D (Paralaje 2.5D):
    El sujeto del frente se mueve a una velocidad y el fondo a otra, creando volumen y profundidad real.
    """
    ffmpeg_exe = get_ffmpeg_path()
    
    from PIL import Image, ImageOps
    try:
        with Image.open(image_path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            img_rgb = np.array(pil_img)
    except Exception as e:
        raise ValueError(f"Error al abrir la imagen '{os.path.basename(image_path)}': {e}\nRuta completa: {image_path}")
        
    ih, iw = img_rgb.shape[:2]
    
    # Escalar imagen para que cubra la resolución destino con margen de seguridad para el movimiento 3D
    scale_factor = max((width * 1.25) / iw, (height * 1.25) / ih)
    nw, nh = int(iw * scale_factor), int(ih * scale_factor)
    img_resized = cv2.resize(img_rgb, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    
    # Recorte centrado con margen
    start_x = (nw - int(width * 1.2)) // 2
    start_y = (nh - int(height * 1.2)) // 2
    canvas_w = int(width * 1.2)
    canvas_h = int(height * 1.2)
    base_img = img_resized[start_y:start_y+canvas_h, start_x:start_x+canvas_w]
    
    # Calcular mapa de profundidad del canvas
    depth_map = estimate_salience_depth_map(base_img)
    
    total_frames = max(1, int(round(duration * fps)))
    
    # Preparar proceso FFmpeg para escribir frames por stdin (alta eficiencia)
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        output_clip_path
    ]
    
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    
    # Crear malla de coordenadas base
    y_coords, x_coords = np.indices((height, width), dtype=np.float32)
    
    # Centro de la imagen destino
    cx, cy = width / 2.0, height / 2.0
    
    # Centro en el canvas fuente
    scx, scy = canvas_w / 2.0, canvas_h / 2.0
    
    for f in range(total_frames):
        t = f / float(total_frames)  # Progreso normalizado de 0.0 a 1.0
        
        # Curva de animación suave (smoothstep easing)
        ease = t * t * (3.0 - 2.0 * t)
        
        # Parámetros del movimiento 3D
        # El sujeto principal (depth=1) se acerca más que el fondo (depth=0)
        fg_zoom = 1.0 + 0.16 * ease
        bg_zoom = 1.0 + 0.04 * ease
        
        # Leve desplazamiento orbital o paneo 3D
        pan_x = 18.0 * (ease - 0.5)
        pan_y = 8.0 * np.sin(np.pi * ease)
        
        # Mapear cada píxel según su profundidad
        # Profundidad interpolada en el canvas
        # Generar mapas de deformación (remap)
        # depth: 0 = fondo, 1 = sujeto
        zoom_at_pixel = bg_zoom + (fg_zoom - bg_zoom) * depth_map[:height, :width]
        shift_x = pan_x * depth_map[:height, :width]
        shift_y = pan_y * depth_map[:height, :width]
        
        map_x = scx + (x_coords - cx) / zoom_at_pixel + shift_x
        map_y = scy + (y_coords - cy) / zoom_at_pixel + shift_y
        
        map_x = map_x.astype(np.float32)
        map_y = map_y.astype(np.float32)
        
        # Remapeo de alta calidad (Warping 3D)
        warped = cv2.remap(base_img, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        warped_bgr = cv2.cvtColor(warped, cv2.COLOR_RGB2BGR)
        
        # Escribir frame directamente en el pipe
        proc.stdin.write(warped_bgr.tobytes())
        
    proc.stdin.close()
    proc.wait()
    
    return output_clip_path
