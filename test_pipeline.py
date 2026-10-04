import os
import shutil
from PIL import Image, ImageDraw, ImageFont
import wave
import math
import struct

from core.sorter import scan_and_sort_images
from core.srt_engine import parse_srt, align_images_with_srt
from core.motion_engine import assign_motions_to_schedule
from core.subtitles import generate_ass_file
from core.renderer import render_video_pipeline, get_audio_duration

def run_test():
    test_dir = os.path.abspath("test_workspace")
    os.makedirs(test_dir, exist_ok=True)
    images_dir = os.path.join(test_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    print("1. Creando imágenes de prueba (1.png, 2.png, 10.png)...")
    colors = [
        ("1.png", (220, 38, 38), "1 - PRIMERA ESCENA"),
        ("2.png", (37, 99, 235), "2 - SEGUNDA ESCENA"),
        ("10.png", (16, 185, 129), "10 - TERCERA ESCENA (NUM 10)")
    ]
    for filename, color, label in colors:
        img = Image.new("RGB", (720, 1280), color=color)
        draw = ImageDraw.Draw(img)
        draw.text((100, 600), label, fill=(255, 255, 255))
        img.save(os.path.join(images_dir, filename))

    print("2. Creando audio de prueba (6 segundos)...")
    audio_path = os.path.join(test_dir, "sample_audio.wav")
    samplerate = 44100
    duration = 6.0
    num_samples = int(duration * samplerate)
    with wave.open(audio_path, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(samplerate)
        for i in range(num_samples):
            # Tono senoidal suave a 440Hz
            value = int(32767.0 * 0.2 * math.sin(2.0 * math.pi * 440.0 * i / samplerate))
            data = struct.pack('<h', value)
            wav_file.writeframes(data)

    print("3. Creando SRT de prueba...")
    srt_content = """1
00:00:00,000 --> 00:00:02,000
ESTA ES LA PRIMERA ESCENA VIRAL

2
00:00:02,000 --> 00:00:04,000
SEGUNDA ESCENA CON SUBTITULOS POP

3
00:00:04,000 --> 00:00:06,000
FINAL CON ZOOM OUT Y MAXIMA RETENCION
"""
    srt_blocks = parse_srt(srt_content)
    print(f"Bloques SRT parseados: {len(srt_blocks)}")

    print("4. Ordenando imágenes naturalmente...")
    images_metadata = scan_and_sort_images(images_dir)
    print("Orden detectado:", [img["filename"] for img in images_metadata])
    assert images_metadata[0]["filename"] == "1.png"
    assert images_metadata[1]["filename"] == "2.png"
    assert images_metadata[2]["filename"] == "10.png"

    print("5. Sincronizando imágenes y tiempos...")
    audio_dur = get_audio_duration(audio_path)
    schedule = align_images_with_srt(images_metadata, srt_blocks, total_audio_duration=audio_dur)
    schedule = assign_motions_to_schedule(schedule, motion_mode="dynamic")

    for s in schedule:
        print(f" -> Imagen: {s['image']['filename']} | Start: {s['start_time']:.2f}s | End: {s['end_time']:.2f}s | Mov: {s['motion_type']}")

    print("6. Generando subtítulos ASS con estilo Hormozi...")
    ass_path = os.path.join(test_dir, "subtitles.ass")
    generate_ass_file(srt_blocks, ass_path, style_key="hormozi", video_width=720, video_height=1280)

    print("7. Renderizando pipeline completo a MP4...")
    output_mp4 = os.path.join(test_dir, "test_output.mp4")
    
    def on_prog(pct, msg):
        print(f"   [{pct:5.1f}%] {msg}")

    render_video_pipeline(
        schedule=schedule,
        audio_path=audio_path,
        output_path=output_mp4,
        subtitle_ass_path=ass_path,
        aspect_ratio="9:16",
        transition_type="fade",
        transition_duration=0.35,
        fps=24,
        progress_callback=on_prog
    )

    if os.path.exists(output_mp4) and os.path.getsize(output_mp4) > 10000:
        print(f"\n[OK] PRUEBA EXITOSA! Video generado: {output_mp4} ({os.path.getsize(output_mp4)} bytes)")
    else:
        print("\n[ERROR] El video no se genero correctamente.")

if __name__ == "__main__":
    run_test()
