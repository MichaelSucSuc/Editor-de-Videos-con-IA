import os
import sys
import tempfile
import threading
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from core.sorter import scan_and_sort_images
from core.srt_engine import parse_srt, align_images_with_srt
from core.voice_aligner import align_transcript_with_acoustic_analysis, transcribe_audio_to_srt
from core.motion_engine import assign_motions_to_schedule
from core.subtitles import SUBTITLE_STYLES, HIGHLIGHT_COLORS, generate_ass_file
from core.transitions import TRANSITION_TYPES
from core.renderer import render_video_pipeline, get_audio_duration
from core.audio_processor import master_voiceover_audio, mix_voiceover_with_bgm, add_transition_sfx_to_audio


# Configuración visual global
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class VideoEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🎬 Editor de Videos con IA (Pro Studio)")
        self.geometry("1100x820")
        self.minsize(980, 720)

        # Variables de estado
        self.images_folder_path = tk.StringVar(value="")
        self.audio_file_path = tk.StringVar(value="")
        self.srt_file_path = tk.StringVar(value="")
        self.output_file_path = tk.StringVar(value="")
        self.bgm_file_path = tk.StringVar(value="")

        self.images_list = []
        self.audio_duration = 0.0
        self.is_rendering = False
        self.is_previewing = False

        # Construir Interfaz
        self._build_ui()

    def _build_ui(self):
        # 1. Header Superior
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#18181b")
        header_frame.pack(fill="x", padx=0, pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_frame, 
            text="🎬 EDITOR DE VIDEOS CON IA", 
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#38bdf8"
        )
        title_lbl.pack(anchor="w", padx=25, pady=(12, 2))

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Crea videos virales de alta retención sincronizando tus imágenes generadas con IA, tu voz y subtítulos.",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8"
        )
        sub_lbl.pack(anchor="w", padx=25, pady=(0, 12))

        # Contenedor con Scroll para albergar todas las secciones cómodamente
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.pack(fill="both", expand=True, padx=20, pady=5)

        # 2. SECCIÓN 1: ARCHIVOS Y RECURSOS
        sec1 = self._create_card("1. Archivos del Proyecto (Fotos, Videos, Audio y Subtítulos)")

        # Fila Medios (Fotos / Videos)
        f_img = ctk.CTkFrame(sec1, fg_color="transparent")
        f_img.pack(fill="x", padx=15, pady=6)
        btn_img = ctk.CTkButton(f_img, text="📁 Seleccionar Medios (Fotos o Videos)", width=260, command=self._select_images_folder)
        btn_img.pack(side="left")

        lbl_filter = ctk.CTkLabel(f_img, text="Tipo:", font=ctk.CTkFont(weight="bold"), padx=10)
        lbl_filter.pack(side="left")

        self.combo_media_type = ctk.CTkComboBox(
            f_img,
            values=[
                "all - Detectar Fotos y Videos",
                "videos - Solo Videos (.mp4, .mov, etc.)",
                "images - Solo Fotos / Imágenes"
            ],
            width=230,
            command=self._on_media_type_changed
        )
        self.combo_media_type.set("all - Detectar Fotos y Videos")
        self.combo_media_type.pack(side="left")

        self.lbl_img_status = ctk.CTkLabel(f_img, text="Ninguna carpeta seleccionada", text_color="#94a3b8", anchor="w")
        self.lbl_img_status.pack(side="left", padx=15, fill="x", expand=True)

        # Fila Audio
        f_aud = ctk.CTkFrame(sec1, fg_color="transparent")
        f_aud.pack(fill="x", padx=15, pady=6)
        btn_aud = ctk.CTkButton(f_aud, text="🎵 Seleccionar Archivo de Audio", width=250, fg_color="#0284c7", hover_color="#0369a1", command=self._select_audio_file)
        btn_aud.pack(side="left")
        self.lbl_aud_status = ctk.CTkLabel(f_aud, text="Ningún archivo de audio seleccionado (.mp3 / .wav)", text_color="#94a3b8", anchor="w")
        self.lbl_aud_status.pack(side="left", padx=15, fill="x", expand=True)

        # Opciones de Audio (Masterización y Calibración Pro)
        f_aud_opts = ctk.CTkFrame(sec1, fg_color="transparent")
        f_aud_opts.pack(fill="x", padx=15, pady=(2, 6))
        self.var_master_audio = ctk.BooleanVar(value=True)
        self.chk_master = ctk.CTkCheckBox(
            f_aud_opts,
            text="🎚️ Modularizar, Calibrar y Masterizar Audio con IA (Ecualizador Pro, Compresor y -14 LUFS)",
            variable=self.var_master_audio,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1"
        )
        self.chk_master.pack(side="left")

        # Fila Música de Fondo (Opcional)
        f_bgm = ctk.CTkFrame(sec1, fg_color="transparent")
        f_bgm.pack(fill="x", padx=15, pady=4)
        btn_bgm = ctk.CTkButton(f_bgm, text="🎼 Música de Fondo (Opcional)", width=250, fg_color="#334155", hover_color="#475569", command=self._select_bgm_file)
        btn_bgm.pack(side="left")
        self.lbl_bgm_status = ctk.CTkLabel(f_bgm, text="Sin música de fondo (Solo voz)", text_color="#94a3b8", anchor="w")
        self.lbl_bgm_status.pack(side="left", padx=15, fill="x", expand=True)

        # Opciones BGM (Volumen y Auto-Ducking)
        f_bgm_opts = ctk.CTkFrame(sec1, fg_color="transparent")
        f_bgm_opts.pack(fill="x", padx=15, pady=(0, 6))

        lbl_bgm_vol = ctk.CTkLabel(f_bgm_opts, text="Volumen Música:", font=ctk.CTkFont(weight="bold"))
        lbl_bgm_vol.pack(side="left", padx=(0, 8))
        self.combo_bgm_vol = ctk.CTkComboBox(f_bgm_opts, values=["12% - Suave (Recomendado)", "18% - Medio", "25% - Alto", "8% - Sutil"], width=200)
        self.combo_bgm_vol.set("12% - Suave (Recomendado)")
        self.combo_bgm_vol.pack(side="left")

        self.var_ducking = ctk.BooleanVar(value=True)
        self.chk_ducking = ctk.CTkCheckBox(
            f_bgm_opts,
            text="🎧 Auto-Ducking Inteligente (Bajar música automáticamente al hablar)",
            variable=self.var_ducking,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.chk_ducking.pack(side="left", padx=20)

        # Fila SRT (Archivo o Texto pegado)
        f_srt = ctk.CTkFrame(sec1, fg_color="transparent")
        f_srt.pack(fill="x", padx=15, pady=6)
        btn_srt = ctk.CTkButton(f_srt, text="📝 Cargar Archivo .SRT", width=250, fg_color="#0d9488", hover_color="#0f766e", command=self._select_srt_file)
        btn_srt.pack(side="left")
        self.lbl_srt_status = ctk.CTkLabel(f_srt, text="Pega tu texto con marcas [00:00] Frase... (Cada marca determina el cambio de imagen)", text_color="#94a3b8", anchor="w")
        self.lbl_srt_status.pack(side="left", padx=15, fill="x", expand=True)

        # Fila de Título y Botones de Copiar/Pegar/Limpiar
        f_srt_tools = ctk.CTkFrame(sec1, fg_color="transparent")
        f_srt_tools.pack(fill="x", padx=15, pady=(4, 2))

        lbl_paste = ctk.CTkLabel(f_srt_tools, text="Guion con marcas [MM:SS] (Controlan los cambios de imagen; la voz se alinea automáticamente):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_paste.pack(side="left")

        btn_copy_srt = ctk.CTkButton(
            f_srt_tools, 
            text="📋 Copiar", 
            width=80, 
            height=26,
            fg_color="#334155", 
            hover_color="#475569",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._copy_srt_clipboard
        )
        btn_copy_srt.pack(side="right", padx=(4, 0))

        btn_paste_srt = ctk.CTkButton(
            f_srt_tools, 
            text="📥 Pegar", 
            width=80, 
            height=26,
            fg_color="#334155", 
            hover_color="#475569",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._paste_srt_clipboard
        )
        btn_paste_srt.pack(side="right", padx=(4, 0))

        btn_clear_srt = ctk.CTkButton(
            f_srt_tools, 
            text="🧹 Limpiar", 
            width=75, 
            height=26,
            fg_color="#334155", 
            hover_color="#475569",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._clear_srt_text
        )
        btn_clear_srt.pack(side="right", padx=(4, 0))

        self.txt_srt = ctk.CTkTextbox(sec1, height=110, font=ctk.CTkFont(family="Consolas", size=11))
        self.txt_srt.pack(fill="x", padx=15, pady=(2, 10))

        # 3. SECCIÓN 2: ESTILO DE SUBTÍTULOS VIRALES
        sec2 = self._create_card("2. Estilos de Subtítulos de Alta Retención")
        
        f_sub_opts = ctk.CTkFrame(sec2, fg_color="transparent")
        f_sub_opts.pack(fill="x", padx=15, pady=(8, 4))

        self.var_sub_enable = ctk.BooleanVar(value=True)
        chk_sub = ctk.CTkCheckBox(f_sub_opts, text="Incrustar Subtítulos en el Video", variable=self.var_sub_enable, font=ctk.CTkFont(weight="bold"))
        chk_sub.pack(side="left")

        lbl_style = ctk.CTkLabel(f_sub_opts, text="Preset Viral:", font=ctk.CTkFont(weight="bold"))
        lbl_style.pack(side="left", padx=(30, 10))

        style_options = [
            "hormozi - Alex Hormozi (Amarillo Neón)",
            "mrbeast - MrBeast (Inclinado Cómic)",
            "vox - Vox Documental (Elegante & Clean)",
            "neon_glow - Cyberpunk Neon (Cyan & Magenta)",
            "minimal - Minimalista Clásico"
        ]
        self.combo_styles = ctk.CTkComboBox(f_sub_opts, values=style_options, width=320)
        self.combo_styles.set(style_options[0])
        self.combo_styles.pack(side="left")

        # Fila 2 de Subtítulos: Ritmo y Posición Vertical Elevada
        f_sub_row2 = ctk.CTkFrame(sec2, fg_color="transparent")
        f_sub_row2.pack(fill="x", padx=15, pady=(4, 10))

        lbl_chunk = ctk.CTkLabel(f_sub_row2, text="Ritmo (Palabras/Pantalla):", font=ctk.CTkFont(weight="bold"))
        lbl_chunk.pack(side="left", padx=(0, 10))

        self.combo_chunk = ctk.CTkComboBox(
            f_sub_row2,
            values=[
                "3 - Dinámico (2 a 3 palabras - Recomendado)",
                "2 - Rápido (1 a 2 palabras - Estilo Shorts)",
                "1 - Ultra Rápido (1 palabra - Palabra por Palabra)",
                "5 - Frases Medias (4 a 5 palabras)",
                "0 - Sin dividir (Frase completa)"
            ],
            width=310
        )
        self.combo_chunk.set("3 - Dinámico (2 a 3 palabras - Recomendado)")
        self.combo_chunk.pack(side="left")

        lbl_pos = ctk.CTkLabel(f_sub_row2, text="Posición:", font=ctk.CTkFont(weight="bold"), padx=15)
        lbl_pos.pack(side="left")

        self.combo_pos = ctk.CTkComboBox(
            f_sub_row2,
            values=[
                "safe_tiktok - Elevado / Tercio Medio (Recomendado TikTok/Reels)",
                "center - Centro de Pantalla (Máximo Impacto)",
                "bottom_low - Inferior Clásico"
            ],
            width=320
        )
        self.combo_pos.set("safe_tiktok - Elevado / Tercio Medio (Recomendado TikTok/Reels)")
        self.combo_pos.pack(side="left")

        # Fila 3 de Subtítulos: Resaltado Karaoke Palabra por Palabra (Word-Level Highlight)
        f_sub_row3 = ctk.CTkFrame(sec2, fg_color="transparent")
        f_sub_row3.pack(fill="x", padx=15, pady=(2, 10))

        lbl_hl = ctk.CTkLabel(f_sub_row3, text="Resaltado Karaoke:", font=ctk.CTkFont(weight="bold"))
        lbl_hl.pack(side="left", padx=(0, 10))

        self.combo_highlight = ctk.CTkComboBox(
            f_sub_row3,
            values=[
                "yellow - Amarillo Neón (Alex Hormozi)",
                "green - Verde Lima Viral",
                "cyan - Cyan Eléctrico Resplandor",
                "orange - Naranja Fuego",
                "none - Sin Resaltar (Color Fijo)"
            ],
            width=310
        )
        self.combo_highlight.set("yellow - Amarillo Neón (Alex Hormozi)")
        self.combo_highlight.pack(side="left")

        lbl_hl_hint = ctk.CTkLabel(
            f_sub_row3, 
            text="✨ Las palabras se iluminan dinámicamente al momento exacto de ser habladas", 
            text_color="#38bdf8", 
            font=ctk.CTkFont(size=11)
        )
        lbl_hl_hint.pack(side="left", padx=15)

        # 4. SECCIÓN 3: MOVIMIENTO DE CÁMARA (KEN BURNS) Y TRANSICIONES
        sec3 = self._create_card("3. Movimiento Dinámico de Imágenes y Transiciones")

        f_cam = ctk.CTkFrame(sec3, fg_color="transparent")
        f_cam.pack(fill="x", padx=15, pady=8)

        lbl_mov = ctk.CTkLabel(f_cam, text="Efectos de Cámara:", font=ctk.CTkFont(weight="bold"), width=160, anchor="w")
        lbl_mov.pack(side="left")

        self.combo_motion = ctk.CTkComboBox(
            f_cam, 
            values=[
                "dynamic - Alternar Dinámicamente (Zoom In, Pan L/R, Zoom Out)",
                "zoom_in - Solo Zoom In Suave",
                "zoom_out - Solo Zoom Out Suave",
                "pan_left_to_right - Solo Paneo Izquierda a Derecha",
                "pan_right_to_left - Solo Paneo Derecha a Izquierda",
                "corner_zoom - Solo Enfoque Rostro / Sujeto"
            ],
            width=430
        )
        self.combo_motion.set("dynamic - Alternar Dinámicamente (Zoom In, Pan L/R, Zoom Out)")
        self.combo_motion.pack(side="left")

        # Checkbox 3D Parallax
        f_3d = ctk.CTkFrame(sec3, fg_color="transparent")
        f_3d.pack(fill="x", padx=15, pady=(4, 8))
        self.var_3d_enable = ctk.BooleanVar(value=False)
        self.chk_3d = ctk.CTkCheckBox(
            f_3d, 
            text="🌌 Activar Efecto 3D Parallax (Profundidad Cinemática y Relieve 2.5D)",
            variable=self.var_3d_enable,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#8b5cf6",
            hover_color="#7c3aed"
        )
        self.chk_3d.pack(side="left")

        # Fila Transición y Aspect Ratio
        f_trans = ctk.CTkFrame(sec3, fg_color="transparent")
        f_trans.pack(fill="x", padx=15, pady=8)

        lbl_tr = ctk.CTkLabel(f_trans, text="Transición:", font=ctk.CTkFont(weight="bold"), width=160, anchor="w")
        lbl_tr.pack(side="left")

        trans_list = [f"{k} - {v}" for k, v in TRANSITION_TYPES.items()]
        self.combo_transitions = ctk.CTkComboBox(f_trans, values=trans_list, width=280)
        self.combo_transitions.set("fade - Disolución Suave (Crossfade)")
        self.combo_transitions.pack(side="left")

        lbl_asp = ctk.CTkLabel(f_trans, text="Formato:", font=ctk.CTkFont(weight="bold"), padx=15)
        lbl_asp.pack(side="left")
        
        self.combo_aspect = ctk.CTkComboBox(
            f_trans,
            values=["9:16 Vertical (TikTok / Reels / Shorts)", "16:9 Horizontal (YouTube)"],
            width=260
        )
        self.combo_aspect.set("9:16 Vertical (TikTok / Reels / Shorts)")
        self.combo_aspect.pack(side="left")

        # Checkbox Efectos de Sonido en Transiciones (SFX Whoosh)
        f_sfx = ctk.CTkFrame(sec3, fg_color="transparent")
        f_sfx.pack(fill="x", padx=15, pady=(4, 8))
        self.var_sfx_enable = ctk.BooleanVar(value=True)
        self.chk_sfx = ctk.CTkCheckBox(
            f_sfx,
            text="🔊 Efectos de Sonido en Transiciones (SFX Whoosh / Swoosh de cine en cada corte)",
            variable=self.var_sfx_enable,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#06b6d4",
            hover_color="#0891b2"
        )
        self.chk_sfx.pack(side="left")

        # 5. SECCIÓN 4: EXPORTACIÓN Y PROGRESO
        sec4 = self._create_card("4. Renderizado y Exportación de Video")

        # Botones de Acción (Vista Previa Rápida y Render Final)
        f_render_btns = ctk.CTkFrame(sec4, fg_color="transparent")
        f_render_btns.pack(fill="x", padx=15, pady=(10, 8))

        self.btn_preview = ctk.CTkButton(
            f_render_btns,
            text="👁️ VISTA PREVIA RÁPIDA (5s)",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46,
            width=260,
            fg_color="#6366f1",
            hover_color="#4f46e5",
            command=self._start_preview
        )
        self.btn_preview.pack(side="left", padx=(0, 10))

        self.btn_render = ctk.CTkButton(
            f_render_btns,
            text="🚀 GENERAR VIDEO MP4 FINAL",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=46,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._start_render
        )
        self.btn_render.pack(side="left", fill="x", expand=True)

        # Barra de progreso
        self.progress_bar = ctk.CTkProgressBar(sec4)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=15, pady=5)

        self.lbl_render_status = ctk.CTkLabel(
            sec4, 
            text="Listo para iniciar.", 
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_render_status.pack(pady=4)

        # Botón para abrir resultado
        self.btn_open_result = ctk.CTkButton(
            sec4,
            text="📂 Abrir Carpeta del Video Exportado",
            state="disabled",
            fg_color="#334155",
            hover_color="#475569",
            command=self._open_output_folder
        )
        self.btn_open_result.pack(pady=(4, 8))

        # Consola de Diagnóstico y Registro en Vivo
        f_log_hdr = ctk.CTkFrame(sec4, fg_color="transparent")
        f_log_hdr.pack(fill="x", padx=15, pady=(8, 2))
        
        lbl_log = ctk.CTkLabel(f_log_hdr, text="Consola de Diagnóstico y Registro en Vivo (Logs):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_log.pack(side="left")

        btn_copy_log = ctk.CTkButton(
            f_log_hdr,
            text="📋 Copiar Log Completo",
            width=140,
            height=24,
            fg_color="#334155",
            hover_color="#475569",
            font=ctk.CTkFont(size=11),
            command=self._copy_logs_clipboard
        )
        btn_copy_log.pack(side="right")

        self.txt_logs = ctk.CTkTextbox(sec4, height=130, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#18181b")
        self.txt_logs.pack(fill="x", padx=15, pady=(2, 12))

    def _create_card(self, title_text: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.main_scroll, fg_color="#27272a", corner_radius=10)
        card.pack(fill="x", pady=8)

        lbl = ctk.CTkLabel(card, text=title_text, font=ctk.CTkFont(size=14, weight="bold"), text_color="#f8fafc")
        lbl.pack(anchor="w", padx=15, pady=(12, 6))

        sep = ctk.CTkFrame(card, height=1, fg_color="#3f3f46")
        sep.pack(fill="x", padx=15, pady=(0, 8))
        return card

    # Handlers de Archivos
    def _select_images_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar Carpeta con Fotos o Videos")
        if folder:
            self.images_folder_path.set(folder)
            self._reload_media_list()

    def _on_media_type_changed(self, choice=None):
        if self.images_folder_path.get():
            self._reload_media_list()

    def _reload_media_list(self):
        folder = self.images_folder_path.get()
        if not folder or not os.path.exists(folder):
            return
        m_filter = self.combo_media_type.get().split(" - ")[0].strip()
        from core.sorter import scan_and_sort_media
        self.images_list = scan_and_sort_media(folder, media_type_filter=m_filter)
        count = len(self.images_list)
        if count > 0:
            first = self.images_list[0]["filename"]
            last = self.images_list[-1]["filename"]
            v_count = sum(1 for x in self.images_list if x.get("media_type") == "video")
            i_count = count - v_count
            det = []
            if v_count > 0:
                det.append(f"{v_count} video(s)")
            if i_count > 0:
                det.append(f"{i_count} foto(s)")
            desc = " y ".join(det) if det else "archivos"
            self.lbl_img_status.configure(
                text=f"✔ {count} archivos ({desc}) ordenados ({first} ... {last})",
                text_color="#4ade80"
            )
            self._append_log(f"📁 Medios detectados: {count} archivos ({desc})")
        else:
            self.lbl_img_status.configure(
                text="⚠ No se encontraron archivos válidos con el filtro actual.",
                text_color="#f87171"
            )

    def _select_audio_file(self):
        file = filedialog.askopenfilename(
            title="Seleccionar Audio",
            filetypes=[("Archivos de Audio", "*.mp3 *.wav *.m4a *.ogg *.aac")]
        )
        if file:
            self.audio_file_path.set(file)
            dur = get_audio_duration(file)
            self.audio_duration = dur
            mins = int(dur // 60)
            secs = int(dur % 60)
            fname = os.path.basename(file)
            self.lbl_aud_status.configure(
                text=f"✔ {fname} (Duración: {mins:02d}:{secs:02d})",
                text_color="#4ade80"
            )

    def _select_bgm_file(self):
        file = filedialog.askopenfilename(
            title="Seleccionar Música de Fondo (BGM)",
            filetypes=[("Archivos de Audio", "*.mp3 *.wav *.m4a *.ogg *.aac")]
        )
        if file:
            self.bgm_file_path.set(file)
            dur = get_audio_duration(file)
            mins = int(dur // 60)
            secs = int(dur % 60)
            fname = os.path.basename(file)
            self.lbl_bgm_status.configure(
                text=f"✔ BGM: {fname} ({mins:02d}:{secs:02d}) [Auto-Ducking Listo]",
                text_color="#4ade80"
            )
            self._append_log(f"🎼 Música de fondo seleccionada: {fname}")

    def _select_srt_file(self):
        file = filedialog.askopenfilename(
            title="Seleccionar Archivo SRT",
            filetypes=[("Archivos de Subtítulos", "*.srt")]
        )
        if file:
            self.srt_file_path.set(file)
            try:
                with open(file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.txt_srt.delete("1.0", "end")
                self.txt_srt.insert("1.0", content)
                self.lbl_srt_status.configure(
                    text=f"✔ {os.path.basename(file)} cargado en el editor",
                    text_color="#4ade80"
                )
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer el archivo SRT: {e}")

    # Funciones de Portapapeles para SRT
    def _copy_srt_clipboard(self):
        text = self.txt_srt.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self._append_log("📋 Texto de subtítulos copiado al portapapeles.")
            messagebox.showinfo("Copiado", "Texto copiado al portapapeles con éxito.")

    def _paste_srt_clipboard(self):
        try:
            text = self.clipboard_get()
            if text:
                self.txt_srt.delete("1.0", "end")
                self.txt_srt.insert("1.0", text)
                self._append_log("📥 Texto pegado desde el portapapeles.")
        except Exception as e:
            messagebox.showwarning("Portapapeles Vacío", "No se encontró texto en el portapapeles.")

    def _clear_srt_text(self):
        self.txt_srt.delete("1.0", "end")
        self._append_log("🧹 Texto de subtítulos limpiado.")


    # Consola de Registro y Diagnóstico
    def _copy_logs_clipboard(self):
        logs = self.txt_logs.get("1.0", "end").strip()
        if logs:
            self.clipboard_clear()
            self.clipboard_append(logs)
            messagebox.showinfo("Log Copiado", "Registro de diagnóstico copiado al portapapeles.")

    def _append_log(self, text: str):
        now_str = datetime.now().strftime("%H:%M:%S")
        line = f"[{now_str}] {text}\n"
        def _insert():
            self.txt_logs.insert("end", line)
            self.txt_logs.see("end")
        self.after(0, _insert)

    def _open_output_folder(self):
        out = self.output_file_path.get()
        if out and os.path.exists(out):
            folder = os.path.dirname(os.path.abspath(out))
            os.startfile(folder)

    # Iniciar Vista Previa Rápida (5 Segundos)
    def _start_preview(self):
        if self.is_rendering or self.is_previewing:
            return

        if not self.images_list:
            messagebox.showwarning("Faltan Imágenes/Videos", "Por favor selecciona una carpeta con imágenes o videos.")
            return

        audio_path = self.audio_file_path.get()
        if not audio_path or not os.path.exists(audio_path):
            messagebox.showwarning("Falta Audio", "Por favor selecciona un archivo de audio válido (.mp3/.wav/etc).")
            return

        preview_out = os.path.join(tempfile.gettempdir(), "vista_previa_editor_ia.mp4")
        self.is_previewing = True
        self.btn_preview.configure(state="disabled")
        self.btn_render.configure(state="disabled")
        self.btn_open_result.configure(state="disabled")

        self._append_log("=" * 60)
        self._append_log("👁️ Generando Vista Previa Rápida de 5 Segundos (Ultrarrápida)...")

        thread = threading.Thread(target=self._run_preview_worker, args=(preview_out,), daemon=True)
        thread.start()

    def _run_preview_worker(self, output_path: str):
        temp_files = []
        try:
            def report_progress(pct: float, msg: str):
                self.after(0, lambda: self._update_gui_progress(pct, msg))
                self._append_log(f"[Vista Previa {int(pct)}%] {msg}")

            audio_path = self.audio_file_path.get()
            actual_audio_path = audio_path
            from core.ffmpeg_utils import get_ffmpeg_path
            import subprocess
            ffmpeg_exe = get_ffmpeg_path()

            # 0. Calibrar y Masterizar Voz
            if self.var_master_audio.get():
                report_progress(5.0, "🎚️ Calibrando y masterizando audio (-14 LUFS)...")
                temp_mastered = output_path + ".temp_pv_master.wav"
                temp_files.append(temp_mastered)
                try:
                    master_voiceover_audio(audio_path, temp_mastered, target_lufs=-14.0)
                    if os.path.exists(temp_mastered):
                        actual_audio_path = temp_mastered
                except Exception as e_m:
                    self._append_log(f"⚠ Aviso en masterización: {e_m}")

            # 1. Parsear SRT y Alinear Medios
            srt_content = self.txt_srt.get("1.0", "end").strip()
            srt_blocks = parse_srt(srt_content, total_duration=self.audio_duration) if srt_content else []

            chunk_val = int(self.combo_chunk.get().split(" - ")[0].strip())
            pos_val = self.combo_pos.get().split(" - ")[0].strip()
            hl_color = self.combo_highlight.get().split(" - ")[0].strip()

            clean_media = [
                img for img in self.images_list 
                if not os.path.basename(img.get("filename", "")).lower().startswith("video_final")
            ]
            if not clean_media:
                clean_media = self.images_list

            schedule = align_images_with_srt(
                images_metadata=clean_media,
                srt_blocks=srt_blocks,
                total_audio_duration=self.audio_duration
            )

            # Truncar schedule para vista previa (máximo 5.0 segundos)
            preview_schedule = []
            curr_dur = 0.0
            for item in schedule:
                rem = 5.0 - curr_dur
                if rem <= 0:
                    break
                item_copy = dict(item)
                if item_copy["duration"] > rem:
                    item_copy["duration"] = rem
                    item_copy["end_time"] = item_copy["start_time"] + rem
                preview_schedule.append(item_copy)
                curr_dur += item_copy["duration"]
            if not preview_schedule and schedule:
                first = dict(schedule[0])
                first["duration"] = 5.0
                preview_schedule = [first]

            motion_choice = self.combo_motion.get().split(" - ")[0].strip()
            preview_schedule = assign_motions_to_schedule(preview_schedule, motion_mode=motion_choice)

            aspect_choice = "9:16" if "9:16" in self.combo_aspect.get() else "16:9"
            trans_choice = self.combo_transitions.get().split(" - ")[0].strip()

            # Cortar audio a 5 segundos exactos
            temp_5s_audio = output_path + ".temp_5s_voice.wav"
            temp_files.append(temp_5s_audio)
            subprocess.run([
                ffmpeg_exe, "-y", "-i", actual_audio_path,
                "-t", "5.0", "-ar", "44100", "-c:a", "pcm_s16le",
                temp_5s_audio
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            actual_audio_path = temp_5s_audio

            # Efectos de Sonido en Transiciones (SFX)
            if self.var_sfx_enable.get():
                trans_times = [it["start_time"] for it in preview_schedule if 0.1 < it.get("start_time", 0) < 4.8]
                if trans_times:
                    report_progress(15.0, f"🔊 Inyectando SFX Whoosh en transiciones...")
                    temp_sfx_audio = output_path + ".temp_sfx.wav"
                    temp_files.append(temp_sfx_audio)
                    add_transition_sfx_to_audio(actual_audio_path, temp_sfx_audio, trans_times, sfx_volume=0.35)
                    if os.path.exists(temp_sfx_audio):
                        actual_audio_path = temp_sfx_audio

            # Música de Fondo (BGM)
            bgm_file = self.bgm_file_path.get()
            if bgm_file and os.path.exists(bgm_file):
                report_progress(20.0, "🎼 Mezclando música de fondo con Auto-Ducking...")
                raw_vol = self.combo_bgm_vol.get().split("%")[0].strip()
                try:
                    bgm_vol = float(raw_vol) / 100.0
                except ValueError:
                    bgm_vol = 0.12
                temp_bgm_audio = output_path + ".temp_bgm.wav"
                temp_files.append(temp_bgm_audio)
                mix_voiceover_with_bgm(actual_audio_path, bgm_file, temp_bgm_audio, bgm_volume=bgm_vol, enable_ducking=self.var_ducking.get())
                if os.path.exists(temp_bgm_audio):
                    actual_audio_path = temp_bgm_audio

            # Subtítulos Estilizados ASS con Karaoke Highlight
            ass_path = None
            if self.var_sub_enable.get() and srt_blocks:
                style_key = self.combo_styles.get().split(" - ")[0].strip()
                ass_path = output_path + ".temp_pv_subtitles.ass"
                temp_files.append(ass_path)

                w = 1080 if aspect_choice == "9:16" else 1920
                h = 1920 if aspect_choice == "9:16" else 1080

                preview_srt = [b for b in srt_blocks if b.get("start_time", 0) < 5.0]
                aligned_subtitle_chunks = align_transcript_with_acoustic_analysis(
                    srt_blocks=preview_srt,
                    audio_path=actual_audio_path,
                    max_words_per_chunk=chunk_val,
                    total_audio_duration=5.0
                )
                generate_ass_file(
                    srt_blocks=aligned_subtitle_chunks,
                    output_ass_path=ass_path,
                    style_key=style_key,
                    video_width=w,
                    video_height=h,
                    max_words_per_subtitle=chunk_val,
                    position_mode=pos_val,
                    highlight_color=hl_color
                )

            # Renderizado Rápido
            report_progress(35.0, "Renderizando vista previa...")
            render_video_pipeline(
                schedule=preview_schedule,
                audio_path=actual_audio_path,
                output_path=output_path,
                subtitle_ass_path=ass_path,
                aspect_ratio=aspect_choice,
                transition_type=trans_choice,
                transition_duration=0.35,
                enable_3d_parallax=self.var_3d_enable.get(),
                fps=30,
                progress_callback=report_progress,
                fast_preview=True
            )

            self.after(0, lambda: self._preview_finished_success(output_path))
        except Exception as e:
            full_trace = traceback.format_exc()
            self._append_log(f"❌ ERROR EN VISTA PREVIA:\n{full_trace}")
            self.after(0, lambda err=str(e): self._preview_finished_error(err))
        finally:
            for tf in temp_files:
                if tf and os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except Exception:
                        pass

    def _preview_finished_success(self, preview_path: str):
        self.is_previewing = False
        self.btn_preview.configure(state="normal")
        self.btn_render.configure(state="normal")
        self.lbl_render_status.configure(text="👁️ ¡Vista previa de 5s lista!", text_color="#a78bfa")
        self._append_log("👁️ ¡Vista previa generada con éxito! Abriendo en reproductor...")
        try:
            os.startfile(preview_path)
        except Exception as e:
            self._append_log(f"Aviso al abrir reproductor: {e}")

    def _preview_finished_error(self, err_msg: str):
        self.is_previewing = False
        self.btn_preview.configure(state="normal")
        self.btn_render.configure(state="normal")
        self.lbl_render_status.configure(text="❌ Error en vista previa.", text_color="#f87171")
        messagebox.showerror("Error en Vista Previa", f"No se pudo generar la vista previa:\n\n{err_msg}")

    # Iniciar Pipeline de Renderizado Final en Hilo Secundario
    def _start_render(self):
        if self.is_rendering or self.is_previewing:
            return

        if not self.images_list:
            messagebox.showwarning("Faltan Imágenes/Videos", "Por favor selecciona una carpeta con imágenes o videos numerados.")
            return

        audio_path = self.audio_file_path.get()
        if not audio_path or not os.path.exists(audio_path):
            messagebox.showwarning("Falta Audio", "Por favor selecciona un archivo de audio válido (.mp3/.wav).")
            return

        default_dir = os.path.dirname(audio_path)
        out_path = filedialog.asksaveasfilename(
            initialdir=default_dir,
            initialfile="video_final_ia.mp4",
            defaultextension=".mp4",
            filetypes=[("Video MP4", "*.mp4")]
        )
        if not out_path:
            return

        self.output_file_path.set(out_path)
        self.is_rendering = True
        self.btn_preview.configure(state="disabled")
        self.btn_render.configure(state="disabled")
        self.btn_open_result.configure(state="disabled")

        self._append_log("=" * 60)
        self._append_log(f"🎬 Iniciando exportación de video final...")
        self._append_log(f"Destino: {out_path}")
        self._append_log(f"Total imágenes detectadas: {len(self.images_list)}")
        self._append_log(f"Audio: {os.path.basename(audio_path)} (Duración: {self.audio_duration:.2f}s)")
        self._append_log(f"Efecto 3D Parallax: {'ACTIVADO' if self.var_3d_enable.get() else 'Desactivado'}")

        thread = threading.Thread(target=self._run_pipeline_worker, args=(out_path,), daemon=True)
        thread.start()

    def _run_pipeline_worker(self, output_path: str):
        temp_files = []
        try:
            def report_progress(pct: float, msg: str):
                self.after(0, lambda: self._update_gui_progress(pct, msg))
                self._append_log(f"[{int(pct)}%] {msg}")

            audio_path = self.audio_file_path.get()
            actual_audio_path = audio_path

            # 0. Modularización, Calibración y Masterización Profesional del Audio
            if self.var_master_audio.get():
                report_progress(2.0, "🎚️ Calibrando y masterizando audio con IA (-14 LUFS, EQ, Compresor)...")
                self._append_log("Masterizando audio: Filtro paso-alto 80Hz, ecualizador de presencia vocal, compresión dinámica y normalización EBU R128 (-14 LUFS)...")
                temp_mastered_audio = os.path.join(os.path.dirname(output_path), "temp_mastered_voice.wav")
                temp_files.append(temp_mastered_audio)
                try:
                    master_voiceover_audio(audio_path, temp_mastered_audio, target_lufs=-14.0)
                    if os.path.exists(temp_mastered_audio):
                        actual_audio_path = temp_mastered_audio
                        self.audio_duration = get_audio_duration(actual_audio_path)
                        self._append_log(f"✔ Audio calibrado y masterizado con éxito (Duración: {self.audio_duration:.2f}s).")
                except Exception as e_m:
                    self._append_log(f"⚠ Aviso en masterización: {e_m}. Se usará audio original.")

            # 1. Leer y parsear SRT (de la caja de texto o archivo)
            srt_content = self.txt_srt.get("1.0", "end").strip()
            srt_blocks = parse_srt(srt_content, total_duration=self.audio_duration) if srt_content else []
            self._append_log(f"Bloques de texto/subtítulos base parseados: {len(srt_blocks)}")

            chunk_val = int(self.combo_chunk.get().split(" - ")[0].strip())
            pos_val = self.combo_pos.get().split(" - ")[0].strip()
            hl_color = self.combo_highlight.get().split(" - ")[0].strip()

            # 2. Alinear imágenes según las marcas exactas del usuario [MM:SS]
            report_progress(3.0, "Sincronizando cambios de imágenes según marcas [MM:SS]...")
            clean_media = [
                img for img in self.images_list 
                if os.path.abspath(img.get("absolute_path", "")) != os.path.abspath(output_path)
                and not os.path.basename(img.get("filename", "")).lower().startswith("video_final")
            ]
            if not clean_media:
                clean_media = self.images_list

            self._append_log(f"Asignando {len(clean_media)} medios según las marcas de tiempo del guion...")
            schedule = align_images_with_srt(
                images_metadata=clean_media,
                srt_blocks=srt_blocks,
                total_audio_duration=self.audio_duration
            )

            # 3. Asignar movimientos
            motion_choice = self.combo_motion.get().split(" - ")[0].strip()
            schedule = assign_motions_to_schedule(schedule, motion_mode=motion_choice)

            # Inyectar Efectos de Sonido (SFX Whoosh) en Transiciones
            if self.var_sfx_enable.get():
                trans_times = [item["start_time"] for item in schedule if item.get("start_time", 0) > 0.1]
                if trans_times:
                    report_progress(4.5, f"🔊 Sincronizando efectos de sonido SFX en {len(trans_times)} transiciones...")
                    temp_sfx_audio = os.path.join(os.path.dirname(output_path), "temp_sfx_audio.wav")
                    temp_files.append(temp_sfx_audio)
                    add_transition_sfx_to_audio(actual_audio_path, temp_sfx_audio, trans_times, sfx_volume=0.35)
                    if os.path.exists(temp_sfx_audio):
                        actual_audio_path = temp_sfx_audio
                        self._append_log(f"✔ Efectos SFX sincronizados en {len(trans_times)} transiciones visuales.")

            # Mezclar Música de Fondo (BGM) con Auto-Ducking Inteligente
            bgm_file = self.bgm_file_path.get()
            if bgm_file and os.path.exists(bgm_file):
                report_progress(5.5, "🎼 Mezclando música de fondo con Auto-Ducking sidechain...")
                raw_vol = self.combo_bgm_vol.get().split("%")[0].strip()
                try:
                    bgm_vol = float(raw_vol) / 100.0
                except ValueError:
                    bgm_vol = 0.12
                temp_bgm_audio = os.path.join(os.path.dirname(output_path), "temp_bgm_audio.wav")
                temp_files.append(temp_bgm_audio)
                duck_enabled = self.var_ducking.get()
                mix_voiceover_with_bgm(actual_audio_path, bgm_file, temp_bgm_audio, bgm_volume=bgm_vol, enable_ducking=duck_enabled)
                if os.path.exists(temp_bgm_audio):
                    actual_audio_path = temp_bgm_audio
                    self._append_log(f"✔ Música de fondo mezclada (Vol: {int(bgm_vol*100)}%, Auto-Ducking: {'Activado' if duck_enabled else 'Desactivado'}).")

            # 4. Aspect Ratio y Transiciones
            aspect_choice = "9:16" if "9:16" in self.combo_aspect.get() else "16:9"
            trans_choice = self.combo_transitions.get().split(" - ")[0].strip()

            # 5. Subtítulos estilizados ASS (Sincronización acústica frase por frase anclada y Karaoke)
            ass_path = None
            if self.var_sub_enable.get() and srt_blocks:
                style_key = self.combo_styles.get().split(" - ")[0].strip()
                temp_ass_dir = os.path.dirname(output_path)
                ass_path = os.path.join(temp_ass_dir, "temp_subtitles.ass")
                temp_files.append(ass_path)
                
                w = 1080 if aspect_choice == "9:16" else 1920
                h = 1920 if aspect_choice == "9:16" else 1080

                report_progress(6.0, "🎙️ Analizando voz y sincronizando subtítulos al milisegundo...")
                self._append_log("Analizando acústicamente la voz y correlacionando con el guion para sincronización perfecta...")
                
                aligned_subtitle_chunks = align_transcript_with_acoustic_analysis(
                    srt_blocks=srt_blocks,
                    audio_path=actual_audio_path,
                    max_words_per_chunk=chunk_val,
                    total_audio_duration=self.audio_duration
                )
                self._append_log(f"✓ Subtítulos sincronizados: {len(aligned_subtitle_chunks)} ráfagas generadas (sin desfases ni solapamiento).")

                generate_ass_file(
                    srt_blocks=aligned_subtitle_chunks,
                    output_ass_path=ass_path,
                    style_key=style_key,
                    video_width=w,
                    video_height=h,
                    max_words_per_subtitle=chunk_val,
                    position_mode=pos_val,
                    audio_path=None,
                    highlight_color=hl_color
                )
                self._append_log(f"Subtítulos estilizados: {style_key} | {chunk_val} pal/pantalla | Resaltado: {hl_color}")

            # 6. Renderizar video
            render_video_pipeline(
                schedule=schedule,
                audio_path=actual_audio_path,
                output_path=output_path,
                subtitle_ass_path=ass_path,
                aspect_ratio=aspect_choice,
                transition_type=trans_choice,
                transition_duration=0.35,
                enable_3d_parallax=self.var_3d_enable.get(),
                fps=30,
                progress_callback=report_progress
            )

            self.after(0, self._render_finished_success)

        except Exception as e:
            full_trace = traceback.format_exc()
            self._append_log(f"❌ ERROR DURANTE EL RENDERIZADO:\n{full_trace}")
            self.after(0, lambda err=str(e), trace=full_trace: self._render_finished_error(err, trace))
        finally:
            for tf in temp_files:
                if tf and os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except Exception:
                        pass
    def _update_gui_progress(self, pct: float, msg: str):
        self.progress_bar.set(pct / 100.0)
        self.lbl_render_status.configure(text=f"{int(pct)}% - {msg}")

    def _render_finished_success(self):
        self.is_rendering = False
        self.btn_render.configure(state="normal")
        self.btn_open_result.configure(state="normal")
        self.lbl_render_status.configure(text="🎉 ¡Video exportado con éxito!", text_color="#4ade80")
        self._append_log("🎉 ¡Video exportado con éxito!")
        messagebox.showinfo("Éxito", "¡El video se ha generado y exportado exitosamente!")

    def _render_finished_error(self, err_msg: str, trace_msg: str = ""):
        self.is_rendering = False
        self.btn_render.configure(state="normal")
        self.lbl_render_status.configure(text=f"❌ Error durante el renderizado.", text_color="#f87171")
        
        detail = (
            f"Ocurrió un error al procesar el video:\n\n"
            f"Motivo: {err_msg}\n\n"
            f"Puedes revisar el registro detallado en la 'Consola de Diagnóstico' abajo "
            f"o hacer clic en 'Copiar Log Completo' para ver la traza técnica."
        )
        messagebox.showerror("Error de Renderizado", detail)

def launch_app():
    app = VideoEditorApp()
    app.mainloop()

if __name__ == "__main__":
    launch_app()
