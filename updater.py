import subprocess

def update_ytdlp():
    try:
        subprocess.run(
            ["pip", "install", "--upgrade", "yt-dlp"],
            check=True
        )
        return True
    except:
        return False