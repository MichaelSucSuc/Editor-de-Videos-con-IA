import os
import sys
import threading
import traceback
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from core.sorter import scan_and_sort_images
from core.srt_engine import parse_srt, align_images_with_srt
from core.motion_engine import assign_motions_to_schedule
from core.subtitles import SUBTITLE_STYLES, generate_ass_file
from core.transitions import TRANSITION_TYPES
from core.renderer import render_video_pipeline, get_audio_duration

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

        self.images_list = []
        self.audio_duration = 0.0
        self.is_rendering = False

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
        sec1 = self._create_card("1. Archivos del Proyecto (Imágenes, Audio y Transcripción)")

        # Fila Imágenes
        f_img = ctk.CTkFrame(sec1, fg_color="transparent")
        f_img.pack(fill="x", padx=15, pady=6)
        btn_img = ctk.CTkButton(f_img, text="📁 Seleccionar Carpeta de Imágenes", width=250, command=self._select_images_folder)
        btn_img.pack(side="left")
        self.lbl_img_status = ctk.CTkLabel(f_img, text="Ninguna carpeta seleccionada", text_color="#94a3b8", anchor="w")
        self.lbl_img_status.pack(side="left", padx=15, fill="x", expand=True)

        # Fila Audio
        f_aud = ctk.CTkFrame(sec1, fg_color="transparent")
        f_aud.pack(fill="x", padx=15, pady=6)
        btn_aud = ctk.CTkButton(f_aud, text="🎵 Seleccionar Archivo de Audio", width=250, fg_color="#0284c7", hover_color="#0369a1", command=self._select_audio_file)
        btn_aud.pack(side="left")
        self.lbl_aud_status = ctk.CTkLabel(f_aud, text="Ningún archivo de audio seleccionado (.mp3 / .wav)", text_color="#94a3b8", anchor="w")
        self.lbl_aud_status.pack(side="left", padx=15, fill="x", expand=True)

        # Fila SRT (Archivo o Texto pegado)
        f_srt = ctk.CTkFrame(sec1, fg_color="transparent")
        f_srt.pack(fill="x", padx=15, pady=6)
        btn_srt = ctk.CTkButton(f_srt, text="📝 Cargar Archivo .SRT", width=250, fg_color="#0d9488", hover_color="#0f766e", command=self._select_srt_file)
        btn_srt.pack(side="left")
        self.lbl_srt_status = ctk.CTkLabel(f_srt, text="Opcional: Carga archivo .srt o pega el texto abajo", text_color="#94a3b8", anchor="w")
        self.lbl_srt_status.pack(side="left", padx=15, fill="x", expand=True)

        # Fila de Título y Botones de Copiar/Pegar/Limpiar
        f_srt_tools = ctk.CTkFrame(sec1, fg_color="transparent")
        f_srt_tools.pack(fill="x", padx=15, pady=(4, 2))

        lbl_paste = ctk.CTkLabel(f_srt_tools, text="Texto / Subtítulos sincronizados (Puedes editarlo directamente):", font=ctk.CTkFont(size=12, weight="bold"))
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

        # 5. SECCIÓN 4: EXPORTACIÓN Y PROGRESO
        sec4 = self._create_card("4. Renderizado y Exportación de Video")

        self.btn_render = ctk.CTkButton(
            sec4,
            text="🚀 GENERAR VIDEO MP4 FINAL",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=46,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._start_render
        )
        self.btn_render.pack(fill="x", padx=15, pady=(10, 8))

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
        folder = filedialog.askdirectory(title="Seleccionar Carpeta con Imágenes IA")
        if folder:
            self.images_folder_path.set(folder)
            self.images_list = scan_and_sort_images(folder)
            count = len(self.images_list)
            if count > 0:
                first = self.images_list[0]["filename"]
                last = self.images_list[-1]["filename"]
                self.lbl_img_status.configure(
                    text=f"✔ {count} imágenes encontradas y ordenadas ({first} ... {last})",
                    text_color="#4ade80"
                )
            else:
                self.lbl_img_status.configure(
                    text="⚠ No se encontraron imágenes válidas en la carpeta seleccionada.",
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

    # Iniciar Pipeline en Hilo Secundario
    def _start_render(self):
        if self.is_rendering:
            return

        if not self.images_list:
            messagebox.showwarning("Faltan Imágenes", "Por favor selecciona una carpeta con imágenes numeradas.")
            return

        audio_path = self.audio_file_path.get()
        if not audio_path or not os.path.exists(audio_path):
            messagebox.showwarning("Falta Audio", "Por favor selecciona un archivo de audio válido (.mp3/.wav).")
            return

        # Preguntar dónde guardar el video final
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
        self.btn_render.configure(state="disabled")
        self.btn_open_result.configure(state="disabled")

        self._append_log("=" * 60)
        self._append_log(f"🎬 Iniciando exportación de video...")
        self._append_log(f"Destino: {out_path}")
        self._append_log(f"Total imágenes detectadas: {len(self.images_list)}")
        self._append_log(f"Audio: {os.path.basename(audio_path)} (Duración: {self.audio_duration:.2f}s)")
        self._append_log(f"Efecto 3D Parallax: {'ACTIVADO' if self.var_3d_enable.get() else 'Desactivado'}")

        # Lanzar proceso en segundo plano
        thread = threading.Thread(target=self._run_pipeline_worker, args=(out_path,), daemon=True)
        thread.start()

    def _run_pipeline_worker(self, output_path: str):
        try:
            def report_progress(pct: float, msg: str):
                self.after(0, lambda: self._update_gui_progress(pct, msg))
                self._append_log(f"[{int(pct)}%] {msg}")

            # 1. Leer y parsear SRT (de la caja de texto o archivo)
            srt_content = self.txt_srt.get("1.0", "end").strip()
            srt_blocks = parse_srt(srt_content) if srt_content else []
            self._append_log(f"Bloques de subtítulos/frases parseados: {len(srt_blocks)}")

            # 2. Alinear imágenes con SRT y duración de audio
            report_progress(2.0, "Sincronizando tiempos de imágenes con el audio...")
            schedule = align_images_with_srt(
                images_metadata=self.images_list,
                srt_blocks=srt_blocks,
                total_audio_duration=self.audio_duration
            )

            # 3. Asignar movimientos
            motion_choice = self.combo_motion.get().split(" - ")[0].strip()
            schedule = assign_motions_to_schedule(schedule, motion_mode=motion_choice)

            # 4. Aspect Ratio y Transiciones
            aspect_choice = "9:16" if "9:16" in self.combo_aspect.get() else "16:9"
            trans_choice = self.combo_transitions.get().split(" - ")[0].strip()

            # 5. Subtítulos estilizados ASS
            ass_path = None
            if self.var_sub_enable.get() and srt_blocks:
                style_key = self.combo_styles.get().split(" - ")[0].strip()
                temp_ass_dir = os.path.dirname(output_path)
                ass_path = os.path.join(temp_ass_dir, "temp_subtitles.ass")
                
                w = 1080 if aspect_choice == "9:16" else 1920
                h = 1920 if aspect_choice == "9:16" else 1080

                chunk_val = int(self.combo_chunk.get().split(" - ")[0].strip())
                pos_val = self.combo_pos.get().split(" - ")[0].strip()

                generate_ass_file(
                    srt_blocks=srt_blocks,
                    output_ass_path=ass_path,
                    style_key=style_key,
                    video_width=w,
                    video_height=h,
                    max_words_per_subtitle=chunk_val,
                    position_mode=pos_val
                )
                self._append_log(f"Subtítulos: {style_key} | {chunk_val} palabras/pantalla | Posición: {pos_val}")

            # 6. Renderizar video
            render_video_pipeline(
                schedule=schedule,
                audio_path=self.audio_file_path.get(),
                output_path=output_path,
                subtitle_ass_path=ass_path,
                aspect_ratio=aspect_choice,
                transition_type=trans_choice,
                transition_duration=0.35,
                enable_3d_parallax=self.var_3d_enable.get(),
                fps=30,
                progress_callback=report_progress
            )

            # Eliminar ASS temporal si existe
            if ass_path and os.path.exists(ass_path):
                try:
                    os.remove(ass_path)
                except Exception:
                    pass

            self.after(0, self._render_finished_success)

        except Exception as e:
            full_trace = traceback.format_exc()
            self._append_log(f"❌ ERROR DURANTE EL RENDERIZADO:\n{full_trace}")
            self.after(0, lambda err=str(e), trace=full_trace: self._render_finished_error(err, trace))

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
