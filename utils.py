import os
import customtkinter as ctk
from PIL import Image
import subprocess


def generate_thumbnail(video_path):

    thumb_folder = "assets/thumbnails"
    os.makedirs(thumb_folder, exist_ok=True)

    name = os.path.splitext(os.path.basename(video_path))[0]
    thumb_path = os.path.join(thumb_folder, f"{name}.png")

    if not os.path.exists(thumb_path):
        try:
            subprocess.run([
                "ffmpeg",
                "-i", video_path,
                "-ss", "00:00:02",
                "-vframes", "1",
                thumb_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            return None

    try:
        img = Image.open(thumb_path)
        img = img.resize((100, 60))
        return ctk.CTkImage(light_image=img, size=(100, 60))
    except:
        return None