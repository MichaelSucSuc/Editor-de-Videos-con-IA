# 🎬 Editor de Videos con IA (Pro Studio Desktop)

Aplicación de escritorio nativa para Windows (100% local, sin servidores ni localhost) para transformar imágenes generadas en serie con IA (`1.png`, `2.png`...), audio de voz y archivos `.srt` en videos de alto impacto con retención viral.

---

## ✨ Características Principales

* 🧠 **Ordenamiento Natural Humano:** Lee automáticamente carpetas de imágenes y las ordena respetando la numeración (`1.png, 2.png ... 9.png, 10.png, 11.png`).
* ⏱️ **Sincronización Inteligente con Audio y SRT:** Asigna duraciones exactas a cada imagen según los tiempos de tu locución (soporta tanto formato SRT como transcripciones con marcas de tiempo `[00:00]`).
* 📋 **Herramientas de Subtítulos:** Botones rápidos de Copiar, Pegar y Limpiar transcripción en 1 clic.
* 🌌 **Efecto 3D Parallax (Checklist Integrado):** Genera volumen, perspectiva y relieve cinemático 2.5D separando el sujeto del fondo.
* 🎥 **Movimiento Dinámico de Cámara (Ken Burns):** Efectos cinematográficos automáticos (*Zoom In, Zoom Out, Paneo Lateral Izquierda/Derecha, Corner Zoom*) para maximizar la retención de los espectadores.
* ⚡ **Transiciones sin Desfase de Audio:** Transiciones fluidas (*Crossfade, Wipe, Slide*) calculadas matemáticamente para no desfasar ni un solo milisegundo tu voz ni tus subtítulos.
* 🎨 **Subtítulos Virales Dinámicos (Estilo TikTok / Hormozi / MrBeast):**
  * 💥 **Ráfagas Cortas de Alto Impacto:** Divide automáticamente frases largas en golpes rápidos de **2 a 3 palabras** (o palabra por palabra) con animación de rebote (*scale pop*) para mantener la retención constante.
  * 📏 **Posición Elevada (Zona Segura TikTok/Reels):** Ubicado en el tercio medio-inferior óptimo, evitando que los botones de descripción o audio tapen el texto.
  * 🎛️ **Control Total:** Selector de ritmo (1 palabra, 2-3 palabras, frases medias) y selector de posición (Elevado, Centro de Pantalla, Clásico).
* 🖥️ **Interfaz Nativa en Modo Oscuro (CustomTkinter):**
  * Sin abrir navegador, sin puertos ni servidores.
  * Barra de progreso en tiempo real y logs en vivo.
  * Botón directo para abrir la carpeta del video exportado.

---

## 🚀 Cómo Iniciar la Aplicación

### Método Rápido (Doble Clic):
Haz doble clic sobre el archivo:
```text
INICIAR_EDITOR.bat
```

### O desde la Terminal:
```bash
python main.py
```

---

## 📁 Estructura del Proyecto

```text
Editor-de-Videos-con-IA/
│
├── core/                        # Motor de procesamiento
│   ├── sorter.py                # Ordenador natural de imágenes
│   ├── srt_engine.py            # Parser de SRT y asignador de tiempos
│   ├── motion_engine.py         # Filtros de movimiento Ken Burns
│   ├── transitions.py           # Cálculo de transiciones sin desfase
│   ├── subtitles.py             # Generador de subtítulos avanzados ASS
│   └── renderer.py              # Pipeline de renderizado con FFmpeg
│
├── gui/                         # Interfaz gráfica de escritorio
│   └── app.py                   # Ventana CustomTkinter modo oscuro
│
├── test_workspace/              # Carpeta con prueba completa generada
│   └── test_output.mp4          # Video de prueba renderizado con éxito
│
├── INICIAR_EDITOR.bat           # Lanzador rápido para Windows
├── main.py                      # Punto de entrada de Python
├── test_pipeline.py             # Script de pruebas automáticas
└── requirements.txt             # Dependencias del proyecto
```