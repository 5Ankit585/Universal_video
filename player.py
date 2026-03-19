import vlc


class VideoPlayer:
    def __init__(self, frame):
        self.instance = vlc.Instance(
            "--avcodec-hw=none",
            "--no-video-title-show"
        )
        self.player = self.instance.media_player_new()
        self.frame = frame

    def load(self, file_path):
        media = self.instance.media_new(file_path)
        self.player.set_media(media)
        self.player.set_hwnd(self.frame.winfo_id())

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def set_volume(self, value):
        self.player.audio_set_volume(int(value))

    def set_position(self, pos):
        self.player.set_position(pos)

    def get_position(self):
        return self.player.get_position()

    def get_time(self):
        return self.player.get_time()

    def get_length(self):
        return self.player.get_length()

    def is_playing(self):
        return self.player.is_playing()

    def set_rate(self, rate):
        self.player.set_rate(rate)