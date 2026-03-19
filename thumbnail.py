from PIL import Image
import os

def get_thumbnail(video_path):
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(video_path)
        frame = clip.get_frame(1)
        img = Image.fromarray(frame)
        img.thumbnail((120, 70))
        clip.close()
        return img
    except:
        return None