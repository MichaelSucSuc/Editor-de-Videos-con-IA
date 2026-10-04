import os
import re
from typing import List, Dict, Any

VALID_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
VALID_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v'}

def natural_sort_key(filename: str):
    """
    Clave de ordenamiento natural humano.
    Convierte cadenas numéricas en enteros para que '10' venga después de '9' y no después de '1'.
    Ejemplo: '2.mp4' -> ['2', 2, '.mp4']
    """
    basename = os.path.basename(filename)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', basename)]

def scan_and_sort_media(folder_path: str, media_type_filter: str = "all") -> List[Dict[str, Any]]:
    """
    Escanea una carpeta, filtra archivos de medios válidos (fotos y/o videos) y los ordena de forma natural.
    media_type_filter: 'all' (fotos y videos), 'images' (solo fotos), 'videos' (solo videos).
    Retorna una lista de diccionarios con metadatos de cada archivo.
    """
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return []

    valid_exts = set()
    if media_type_filter == "images":
        valid_exts = VALID_IMAGE_EXTENSIONS
    elif media_type_filter == "videos":
        valid_exts = VALID_VIDEO_EXTENSIONS
    else:  # "all"
        valid_exts = VALID_IMAGE_EXTENSIONS.union(VALID_VIDEO_EXTENSIONS)

    ignored_names = {"video_final_ia.mp4", "output.mp4", "video_final.mp4"}
    media_files = []
    for entry in os.scandir(folder_path):
        if entry.is_file():
            lower_name = entry.name.lower()
            if lower_name in ignored_names or lower_name.startswith("temp_") or lower_name.startswith("video_final"):
                continue
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in valid_exts:
                media_files.append(entry.path)

    # Ordenar con la clave natural (1, 2, ... 9, 10)
    media_files.sort(key=natural_sort_key)

    result = []
    for idx, path in enumerate(media_files, start=1):
        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower()
        
        # Extraer el primer número que aparezca en el nombre si existe
        num_match = re.search(r'\d+', filename)
        extracted_num = int(num_match.group()) if num_match else idx
        
        is_video = ext in VALID_VIDEO_EXTENSIONS

        result.append({
            "order_index": idx,
            "extracted_number": extracted_num,
            "filename": filename,
            "absolute_path": os.path.abspath(path),
            "size_bytes": os.path.getsize(path),
            "media_type": "video" if is_video else "image"
        })

    return result

# Mantener compatibilidad con llamadas existentes a scan_and_sort_images
def scan_and_sort_images(folder_path: str) -> List[Dict[str, Any]]:
    return scan_and_sort_media(folder_path, media_type_filter="all")

if __name__ == "__main__":
    test_names = ["10.mp4", "1.png", "2.mov", "video_20.mp4", "img_3.jpg"]
    sorted_test = sorted(test_names, key=natural_sort_key)
    print("Test ordenamiento natural:", sorted_test)
