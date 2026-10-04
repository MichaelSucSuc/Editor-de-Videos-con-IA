import os
import re
from typing import List, Dict, Any

VALID_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}

def natural_sort_key(filename: str):
    """
    Clave de ordenamiento natural humano.
    Convierte cadenas numéricas en enteros para que '10' venga después de '9' y no después de '1'.
    Ejemplo: '2.png' -> ['2', 2, '.png']
    """
    basename = os.path.basename(filename)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', basename)]

def scan_and_sort_images(folder_path: str) -> List[Dict[str, Any]]:
    """
    Escanea una carpeta, filtra archivos de imagen válidos y los ordena de forma natural.
    Retorna una lista de diccionarios con metadatos de cada imagen.
    """
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return []

    image_files = []
    for entry in os.scandir(folder_path):
        if entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in VALID_IMAGE_EXTENSIONS:
                image_files.append(entry.path)

    # Ordenar con la clave natural
    image_files.sort(key=natural_sort_key)

    result = []
    for idx, path in enumerate(image_files, start=1):
        filename = os.path.basename(path)
        # Extraer el primer número que aparezca en el nombre si existe
        num_match = re.search(r'\d+', filename)
        extracted_num = int(num_match.group()) if num_match else idx

        result.append({
            "order_index": idx,
            "extracted_number": extracted_num,
            "filename": filename,
            "absolute_path": os.path.abspath(path),
            "size_bytes": os.path.getsize(path)
        })

    return result

if __name__ == "__main__":
    # Test simple
    test_names = ["10.png", "1.jpg", "2.webp", "img_20.png", "img_3.png"]
    sorted_test = sorted(test_names, key=natural_sort_key)
    print("Test ordenamiento natural:", sorted_test)
