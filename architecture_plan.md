# 🎬 Editor de Videos con IA - Blueprint y Arquitectura (App de Escritorio)

## 1. Visión General del Sistema
Una **aplicación de escritorio nativa para Windows (100% local, sin servidores ni localhost)** diseñada para transformar una serie de imágenes generadas por IA (`1.png`, `2.png`...), un archivo de audio y una transcripción `.srt` en videos de alto impacto con retención viral (estilo Shorts / TikTok / Reels / Documentales de YouTube).

---

## 2. Diagrama de Arquitectura Modular

```
┌────────────────────────────────────────────────────────────────────────┐
│             INTERFAZ GRÁFICA DE ESCRITORIO (CustomTkinter)             │
│                                                                        │
│  [📁 Carpeta Imágenes]  [🎵 Audio (.mp3/.wav)]  [📝 Archivo/Texto SRT]  │
│  ────────────────────────────────────────────────────────────────────  │
│  [🎨 Presets Subtítulos]    [🎥 Movimientos Ken Burns] [✨ Transición] │
│  - Hormozi Pop             - Zoom In / Out            - Crossfade      │
│  - MrBeast Inclinado       - Paneo Lateral            - Whip Pan       │
│  - Vox Documental          - Corner Zoom              - Corte Directo  │
│  ────────────────────────────────────────────────────────────────────  │
│  [ 📺 Vista Previa de Asignación de Tiempos: Imagen ↔ Frase SRT ]     │
│  [ 🚀 BOTÓN DE EXPORTACIÓN CON BARRA DE PROGRESO Y LOGS EN VIVO ]      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    NÚCLEO DE PROCESAMIENTO (Python)                    │
│                                                                        │
│  1. Natural File Sorter                                                │
│     - Algoritmo de ordenamiento humano (1, 2, ... 9, 10, 11)           │
│                                                                        │
│  2. SRT & Timing Engine                                                │
│     - Parser de tiempos milimétricos del archivo .srt                  │
│     - Cálculo de duraciones exactas por cada imagen                    │
│                                                                        │
│  3. Motion & Camera Engine (Ken Burns Filter Builder)                  │
│     - Expresiones matemáticas de FFmpeg (zoompan con easing)           │
│     - Alternancia automática de movimientos (Zoom In/Out, Pan L/R)     │
│                                                                        │
│  4. Transition Engine (Sin desfase de audio)                           │
│     - Compensación de superposición milimétrica                        │
│                                                                        │
│  5. Advanced Subtitle Compiler (.ASS Engine)                           │
│     - Tipografías integradas (Montserrat, Komika, Inter)               │
│     - Animación de rebote (bounce/scale pop), colores neón y sombras    │
│                                                                        │
│  6. FFmpeg Runner & Hardware Acceleration Engine                       │
│     - Detección de binario portátil / sistema                          │
│     - Renderizado acelerado por GPU (NVIDIA NVENC / Intel QSV / CPU)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   SALIDA FINAL: video_generado.mp4                     │
│         (1080x1920 Vertical 9:16 o 1920x1080 Horizontal 16:9)         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Especificación Técnica de los Módulos

### Módulo 1: Ordenador Natural de Archivos (`core/sorter.py`)
* Lee cualquier formato común: `.png`, `.jpg`, `.jpeg`, `.webp`.
* Utiliza ordenamiento natural basado en expresiones regulares:
  * Entradas: `['img10.png', 'img1.png', 'img2.png']`
  * Salida garantizada: `['img1.png', 'img2.png', 'img10.png']`.

### Módulo 2: Motor de Tiempos y Sincronización SRT (`core/srt_engine.py`)
* Parsea bloques `.srt` extrayendo:
  * `index`: Número del bloque.
  * `start_time`: Segundo y milisegundo de inicio.
  * `end_time`: Segundo y milisegundo de finalización.
  * `duration`: Duración exacta del bloque.
  * `text`: Frase o palabras del bloque.
* Asigna a la imagen `N` el tiempo del bloque `N` (o permite agrupar varios bloques a una misma imagen si hay más bloques que imágenes).

### Módulo 3: Motor de Movimiento Cinemático (`core/motion_engine.py`)
Genera las expresiones de filtro `zoompan` de FFmpeg optimizadas para suavidad (sin saltos bruscos):
* **Slow Zoom In:** Comienza en zoom 1.0 y escala suavemente a 1.25 enfocado al centro o al sujeto.
* **Slow Zoom Out:** Comienza en 1.25 y se aleja a 1.0.
* **Pan Left to Right:** Zoom 1.15 con desplazamiento horizontal suave de izquierda a derecha.
* **Pan Right to Left:** Zoom 1.15 con desplazamiento horizontal de derecha a izquierda.
* **Corner Zoom:** Zoom dirigido hacia la esquina superior/inferior.

### Módulo 4: Motor de Transiciones No Destructivas (`core/transitions.py`)
* Aplica transiciones entre imagen A e imagen B utilizando filtros complejos de FFmpeg (`xfade`).
* **Regla de sincronía:** La transición se aplica mediante *lead-in* o centrado simétrico exacto, de modo que el punto medio de la transición coincida con la marca de tiempo del SRT. La voz jamás pierde el ritmo.

### Módulo 5: Generador de Subtítulos de Alta Retención (`core/subtitles.py`)
Genera archivos en formato `.ass` (Advanced SubStation Alpha) que permiten control total de estilos que luego se queman (*hardsub*) en el video:
1. **Hormozi Style:** Tipografía pesada, mayúsculas, caja amarilla o verde neón, rebote y contorno oscuro.
2. **MrBeast Style:** Letras estilo cómic, rotación dinámica de 3 grados, bordes dobles negros.
3. **Vox Documentary:** Tipografía minimalista con caja semitransparente oscura y aparición elegante.
4. **Neon Glow Karaoke:** Resplandor exterior en tonos cyan/magenta.

### Módulo 6: Orquestador FFmpeg (`core/renderer.py`)
* Autodetecta si FFmpeg está en el sistema o incluye un gestor que lo descarga o utiliza de forma autónoma.
* Detección de aceleración por hardware (NVENC para GPUs NVIDIA, QSV para Intel, o libx264 para CPU).
* Reporte en tiempo real de porcentaje de renderizado hacia la interfaz gráfica.

---

## 4. Diseño de la Interfaz Gráfica (CustomTkinter)

* **Tema:** Dark Mode elegante (paleta Obsidian/Slate con acentos en Azul Eléctrico y Verde Neón).
* **Sección 1 (Entrada de Archivos):**
  * Botón selector de carpeta de imágenes (con conteo en vivo: *"18 imágenes encontradas"*).
  * Botón selector de archivo de audio (`.mp3` o `.wav`).
  * Selector de archivo `.srt` o botón *"Pegar texto SRT"* que abre un editor rápido.
* **Sección 2 (Estilo de Subtítulos):**
  * Tarjetas seleccionables con preview visual de la tipografía y colores.
  * Selector de posición del subtítulo (inferior, centro, tercio superior).
* **Sección 3 (Movimiento y Transiciones):**
  * Interruptor para *"Movimiento dinámico aleatorio (recomendado)"* o selección manual.
  * Menú desplegable de transiciones (*Crossfade, Whip Pan, Dissolve, Ninguna*).
  * Selector de relación de aspecto (📱 9:16 Vertical para TikTok/Reels o 💻 16:9 Horizontal).
* **Sección 4 (Consola y Render):**
  * Botón gigante: `[ 🎬 GENERAR VIDEO ]`.
  * Barra de progreso interactiva con porcentaje y tiempo estimado.
  * Botón para abrir la carpeta del video resultante una vez finalizado.

---

## 5. Fases de Construcción

1. **Paso 1: Entorno y Dependencias Base**
   * Configuración de Python, CustomTkinter y FFmpeg autónomo.
2. **Paso 2: Motores de Núcleo (Core)**
   * Sorter natural + Parser SRT + Generador de filtros Ken Burns + Subtítulos ASS.
3. **Paso 3: Interfaz Gráfica de Escritorio**
   * Creación de la ventana principal con todos los controles y validación de archivos.
4. **Paso 4: Enlace y Pruebas Reales**
   * Renderizado de prueba con imágenes y audio muestra para validar tiempos, transiciones y calidad.
