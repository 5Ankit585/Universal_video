import customtkinter as ctk

class MiniPlayer(ctk.CTkToplevel):

    def __init__(self, master, player):
        super().__init__(master)

        self.player = player

        self.geometry("400x250")
        self.attributes("-topmost", True)

        self.video_frame = ctk.CTkFrame(self)
        self.video_frame.pack(fill="both", expand=True)

        self.after(100, self.attach_video)

    def attach_video(self):
        self.player.set_hwnd(self.video_frame.winfo_id())