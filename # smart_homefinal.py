# smart_home.py

import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import queue
import time
import json
import os
import difflib

# Optional imports
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except Exception:
    sr = None
    SR_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except Exception:
    pyttsx3 = None
    TTS_AVAILABLE = False

# pvporcupine is optional (wake-word). Installation is platform-specific.
try:
    import pvporcupine
    import pyaudio
    PORCUPINE_AVAILABLE = True
except Exception:
    pvporcupine = None
    pyaudio = None
    PORCUPINE_AVAILABLE = False

# Constants and Devices
WINDOW_SIZE = "980x640"
APP_TITLE = "Smart Home — Complete"

DEVICES = [
    {"id": "light", "label": "Living Room Light", "type": "switch"},
    {"id": "fan", "label": "Ceiling Fan", "type": "switch"},
    {"id": "ac", "label": "Air Conditioner", "type": "switch"},
    {"id": "door", "label": "Front Door", "type": "lock"},
    {"id": "heater", "label": "Heater", "type": "switch"},
]

STATE_FILE = "sh_state.json"


# -------------------------
# Persistence utilities
# -------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print("Warning: could not save state:", e)


# -------------------------
# TTS helper (optional)
# -------------------------
class TTS:
    def __init__(self):
        self.engine = None
        if TTS_AVAILABLE:
            try:
                self.engine = pyttsx3.init()
                try:
                    self.engine.setProperty("rate", 160)
                    self.engine.setProperty("volume", 1.0)
                except Exception:
                    pass
            except Exception:
                self.engine = None

    def speak(self, text):
        if not self.engine:
            return
        def _run():
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception:
                print("TTS error for text:", text)
        threading.Thread(target=_run, daemon=True).start()


# -------------------------
# Voice Engine (SpeechRecognition)
# -------------------------
class VoiceEngine:
    """
    Threaded voice listening using SpeechRecognition (Google API fallback).
    Sends recognized text as commands via app.queue: ('transcript', text) and ('command', matched_command)
    """
    def __init__(self, app_queue, log_fn, ui_state_fn):
        self.queue = app_queue
        self.log = log_fn
        self.ui_state = ui_state_fn
        self.running = False
        self.thread = None
        self.microphone_index = None

        self.CANONICAL = [
            "turn on light",
            "turn off light",
            "turn on fan",
            "turn off fan",
            "turn on ac",
            "turn off ac",
            "lock door",
            "unlock door",
            "good morning",
            "good night",
            "away mode",
            "status",
        ]

        if not SR_AVAILABLE:
            self.log("SpeechRecognition not available — voice disabled")

    def set_microphone(self, index):
        self.microphone_index = index
        self.log(f"Microphone index set to {index}")

    def start(self):
        if not SR_AVAILABLE:
            self.log("Cannot start voice engine: SpeechRecognition not installed.")
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        self.log("Voice engine started")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.log("Voice engine stopped")

    def _fuzzy_match(self, txt):
        txt = txt.lower().strip()
        match = difflib.get_close_matches(txt, self.CANONICAL, n=1, cutoff=0.55)
        if match:
            return match[0]
        for c in self.CANONICAL:
            if c in txt or any(word in txt for word in c.split()):
                return c
        return None

    def _listen_loop(self):
        recognizer = sr.Recognizer()
        while self.running:
            try:
                if self.microphone_index is None:
                    mic = sr.Microphone()
                else:
                    mic = sr.Microphone(device_index=self.microphone_index)

                self.ui_state("listening")
                with mic as source:
                    try:
                        recognizer.adjust_for_ambient_noise(source, duration=1.2)
                    except Exception:
                        pass
                    try:
                        audio = recognizer.listen(source, timeout=5, phrase_time_limit=7)
                    except sr.WaitTimeoutError:
                        self.ui_state("idle")
                        continue

                self.ui_state("processing")
                text = None
                try:
                    text = recognizer.recognize_google(audio)
                except sr.UnknownValueError:
                    self.log("Could not understand audio (UnknownValueError)")
                except sr.RequestError as e:
                    self.log(f"Speech API request error: {e}")
                except Exception as e:
                    self.log(f"Recognition error: {e}")

                if text:
                    text = text.strip()
                    self.queue.put(("transcript", text))
                    matched = self._fuzzy_match(text)
                    if matched:
                        self.queue.put(("command", matched))
                    else:
                        self.queue.put(("command_unknown", text))
                self.ui_state("idle")
            except Exception as e:
                self.log(f"Voice loop exception: {e}")
                self.ui_state("idle")
                time.sleep(0.5)


# -------------------------
# Wake-word engine (fallback)
# -------------------------
class WakeWordEngine:
    """
    If pvporcupine available, uses it (keyword selection limited). Otherwise fallback: short listens and checks for presence of phrase "hey home".
    Calls a callback on wake detected.
    """
    def __init__(self, wake_callback, log_fn, ui_state_fn):
        self.wake_callback = wake_callback
        self.log = log_fn
        self.ui_state = ui_state_fn
        self.running = False
        self.thread = None
        self._stop = threading.Event()

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log("Wake-word engine started")

    def stop(self):
        if not self.running:
            return
        self._stop.set()
        self.running = False
        self.log("Wake-word engine stopped")

    def _run(self):
        if PORCUPINE_AVAILABLE:
            try:
                porcupine = pvporcupine.create(keywords=["hey google"])
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    rate=porcupine.sample_rate,
                    channels=1,
                    format=pyaudio.paInt16,
                    input=True,
                    frames_per_buffer=porcupine.frame_length,
                )
                self.log("Porcupine wake-word initialized")
                while not self._stop.is_set():
                    pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
                    pcm_unpacked = pvporcupine.util.buffer_to_int16(pcm)
                    res = porcupine.process(pcm_unpacked)
                    if res >= 0:
                        self.log("Wake-word detected (porcupine)")
                        self.ui_state("wake_detected")
                        try:
                            self.wake_callback()
                        except Exception:
                            pass
                        time.sleep(1.0)
                    time.sleep(0.01)
                try:
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
                except Exception:
                    pass
                return
            except Exception as e:
                self.log(f"Porcupine error: {e}")

        # fallback
        if not SR_AVAILABLE:
            self.log("Wake-word fallback unavailable: SpeechRecognition not installed")
            return

        recognizer = sr.Recognizer()
        try:
            mic = sr.Microphone()
        except Exception as e:
            self.log(f"Wake-word mic error: {e}")
            return

        with mic as source:
            try:
                recognizer.adjust_for_ambient_noise(source, duration=1.0)
            except Exception:
                pass

        self.log("Wake-word fallback listening for 'hey home'")

        while not self._stop.is_set():
            try:
                with mic as source:
                    try:
                        audio = recognizer.listen(source, timeout=4, phrase_time_limit=2)
                    except sr.WaitTimeoutError:
                        continue
                try:
                    text = recognizer.recognize_google(audio).lower()
                    self.log(f"Wake fallback heard: {text}")
                    if "hey home" in text or "hey honey" in text or text.strip() == "home":
                        self.ui_state("wake_detected")
                        try:
                            self.wake_callback()
                        except Exception:
                            pass
                        time.sleep(1.0)
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    self.log(f"Wake fallback API error: {e}")
                    time.sleep(1.0)
                except Exception as e:
                    self.log(f"Wake fallback recognition error: {e}")
                    time.sleep(1.0)
            except Exception as e:
                self.log(f"Wake fallback loop error: {e}")
                time.sleep(1.0)


# -------------------------
# Core GUI + Integration
# -------------------------
class SmartHomeApp:
    def __init__(self, master):
        self.master = master
        self.master.title(APP_TITLE)
        self.master.geometry(WINDOW_SIZE)
        self.master.configure(bg="#0b1220")

        self.queue = queue.Queue()
        persisted = load_state()
        self.device_state = persisted.get("devices", {d["id"]: False for d in DEVICES})
        if "door" not in self.device_state:
            self.device_state["door"] = False

        self.tts = TTS()
        self.voice_engine = VoiceEngine(self.queue, self._log, self._set_ui_state)
        self.wake_engine = WakeWordEngine(self._on_wake_detected, self._log, self._set_ui_state)

        self._build_ui()
        self.master.after(150, self._process_queue)

    def _build_ui(self):
        top = tk.Frame(self.master, bg="#071029", height=64)
        top.pack(fill="x")
        tk.Label(
            top,
            text="Smart Home — Final",
            font=("Segoe UI", 18, "bold"),
            fg="#e6eef7",
            bg="#071029",
        ).pack(side="left", padx=14, pady=10)

        main = tk.Frame(self.master, bg="#0b1220")
        main.pack(fill="both", expand=True, padx=12, pady=10)

        left = tk.Frame(main, bg="#0b1220")
        left.pack(side="left", fill="y", padx=(0, 8))
        tk.Label(
            left, text="Devices", bg="#0b1220", fg="#e6eef7", font=("Segoe UI", 14, "bold")
        ).pack(anchor="w")

        self.device_panels = {}
        for d in DEVICES:
            panel = tk.Frame(left, bg="#0b1220", bd=1, relief="ridge", padx=8, pady=8)
            panel.pack(fill="x", pady=6)
            lbl = tk.Label(panel, text=d["label"], font=("Segoe UI", 12, "bold"),
                           bg="#0b1220", fg="#f3f4f6")
            lbl.pack(anchor="w")
            state_lbl = tk.Label(panel, text="OFF", font=("Segoe UI", 11),
                                 bg="#0b1220", fg="#ef4444")
            state_lbl.pack(anchor="w")
            btns = tk.Frame(panel, bg="#0b1220")
            btns.pack(anchor="e", pady=6)
            on_btn = tk.Button(btns, text="On", width=8,
                               command=lambda id=d["id"]: self.set_device(id, True))
            off_btn = tk.Button(btns, text="Off", width=8,
                                command=lambda id=d["id"]: self.set_device(id, False))
            on_btn.pack(side="left", padx=4)
            off_btn.pack(side="left", padx=4)
            self.device_panels[d["id"]] = {"state_lbl": state_lbl,
                                           "on_btn": on_btn, "off_btn": off_btn}

        middle = tk.Frame(main, bg="#071029")
        middle.pack(side="left", fill="both", expand=True, padx=8)

        scenes = tk.Frame(middle, bg="#071029")
        scenes.pack(fill="x")
        tk.Label(scenes, text="Scenes", bg="#071029", fg="#e6eef7",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        sframe = tk.Frame(scenes, bg="#071029")
        sframe.pack(anchor="w", pady=8)
        tk.Button(sframe, text="Good Morning", width=14,
                  command=self.scene_good_morning).pack(side="left", padx=6)
        tk.Button(sframe, text="Good Night", width=14,
                  command=self.scene_good_night).pack(side="left", padx=6)
        tk.Button(sframe, text="Away", width=14,
                  command=self.scene_away).pack(side="left", padx=6)

        cmd_box = tk.LabelFrame(middle, text="Text Command", bg="#071029",
                                fg="#e6eef7", font=("Segoe UI", 11))
        cmd_box.pack(fill="both", expand=True, pady=8)
        cmd_box.configure(labelanchor="n")
        self.cmd_entry = tk.Entry(cmd_box, font=("Segoe UI", 12))
        self.cmd_entry.pack(fill="x", padx=12, pady=10)
        self.cmd_entry.bind("<Return>", lambda e: self._on_text_command())
        btns = tk.Frame(cmd_box, bg="#071029")
        btns.pack(pady=6)
        tk.Button(btns, text="Send", width=12, command=self._on_text_command).pack(side="left", padx=6)
        tk.Button(btns, text="Help", width=12, command=self.show_help).pack(side="left", padx=6)

        right = tk.Frame(main, bg="#071029", width=340)
        right.pack(side="right", fill="y", padx=(8, 0))
        tk.Label(right, text="Activity Log", bg="#071029", fg="#e6eef7",
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        self.log_area = scrolledtext.ScrolledText(right, width=42, height=22,
                                                  state="disabled", bg="#0b1220", fg="#e6eef7")
        self.log_area.pack(pady=6)

        controls = tk.Frame(right, bg="#071029")
        controls.pack(fill="x", pady=6)
        tk.Label(controls, text="Microphone:", bg="#071029", fg="#cbd5e1").pack(anchor="w")
        self.mic_var = tk.StringVar(value="(default)")
        self.mic_menu = tk.OptionMenu(controls, self.mic_var, "(default)")
        self.mic_menu.configure(width=30)
        self.mic_menu.pack(anchor="w", padx=4, pady=4)
        self._populate_mic_list()

        btn_frame = tk.Frame(controls, bg="#071029")
        btn_frame.pack(fill="x", pady=4)
        self.voice_btn = tk.Button(btn_frame, text="Start Voice", width=14, command=self._toggle_voice)
        self.voice_btn.pack(side="left", padx=6)
        self.wake_btn = tk.Button(btn_frame, text="Start Wake-word", width=14, command=self._toggle_wake)
        self.wake_btn.pack(side="left", padx=6)

        bottom = tk.Frame(self.master, bg="#071029", height=50)
        bottom.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(bottom, textvariable=self.status_var, bg="#071029", fg="#cbd5e1").pack(side="left", padx=12)

        self._update_device_ui()

    def _populate_mic_list(self):
        menu = self.mic_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="(default)", command=lambda v="(default)": self._on_mic_selected(v))
        if SR_AVAILABLE:
            try:
                names = sr.Microphone.list_microphone_names()
                for i, name in enumerate(names):
                    label = f"{i}: {name}"
                    menu.add_command(label=label, command=lambda v=i: self._on_mic_selected(v))
            except Exception as e:
                self._log(f"Could not list microphones: {e}")
        else:
            self._log("SpeechRecognition not installed: microphone selection disabled")

    def _on_mic_selected(self, value):
        if value == "(default)":
            self.mic_var.set("(default)")
            self.voice_engine.set_microphone(None)
        else:
            self.mic_var.set(str(value))
            self.voice_engine.set_microphone(int(value))

    def _on_text_command(self):
        text = self.cmd_entry.get().strip()
        if not text:
            return
        self.cmd_entry.delete(0, "end")
        self._log(f"Typed: {text}")
        self._handle_command_text(text)

    def _handle_command_text(self, text):
        cmd = text.lower().strip()
        if "turn on" in cmd and "light" in cmd:
            self.set_device("light", True)
            return
        if "turn off" in cmd and "fan" in cmd:
            self.set_device("fan", False)
            return
        if "lock" in cmd and "door" in cmd:
            self.set_device("door", False)
            return
        if "unlock" in cmd and "door" in cmd:
            self.set_device("door", True)
            return
        if "good morning" in cmd:
            self.scene_good_morning()
            return
        if "good night" in cmd or "goodnight" in cmd:
            self.scene_good_night()
            return
        if "away" in cmd:
            self.scene_away()
            return
        if "status" in cmd or "report" in cmd:
            self.report_status()
            return

        matched = difflib.get_close_matches(cmd, self.voice_engine.CANONICAL, n=1, cutoff=0.55)
        if matched:
            self._log(f"Interpreted as: {matched[0]}")
            self._execute_canonical(matched[0])
            return

        self._log("Sorry — command not recognized. Try 'Help' for examples.")
        self.tts.speak("Sorry, I did not understand that")

    def _execute_canonical(self, canonical):
        if canonical == "turn on light":
            self.set_device("light", True)
        elif canonical == "turn off light":
            self.set_device("light", False)
        elif canonical == "turn on fan":
            self.set_device("fan", True)
        elif canonical == "turn off fan":
            self.set_device("fan", False)
        elif canonical == "turn on ac":
            self.set_device("ac", True)
        elif canonical == "turn off ac":
            self.set_device("ac", False)
        elif canonical == "lock door":
            self.set_device("door", False)
        elif canonical == "unlock door":
            self.set_device("door", True)
        elif canonical == "good morning":
            self.scene_good_morning()
        elif canonical == "good night":
            self.scene_good_night()
        elif canonical == "away mode":
            self.scene_away()
        elif canonical == "status":
            self.report_status()
        else:
            self._log(f"Canonical command not implemented: {canonical}")

    def set_device(self, device_id, value):
        if device_id not in self.device_state:
            self._log(f"Unknown device: {device_id}")
            return
        self.device_state[device_id] = bool(value)
        self._update_device_ui()
        save_state({"devices": self.device_state})
        self._log(f"{device_id} -> {self._human_state(device_id)}")
        self.tts.speak(f"{device_id} set to {self._human_state(device_id)}")

    def _human_state(self, device_id):
        if device_id == "door":
            return "Unlocked" if self.device_state[device_id] else "Locked"
        return "ON" if self.device_state[device_id] else "OFF"

    def _update_device_ui(self):
        for did, panel in self.device_panels.items():
            s = self.device_state.get(did, False)
            label = panel["state_lbl"]
            if did == "door":
                label.config(text=("Unlocked" if s else "Locked"),
                             fg="#10b981" if s else "#ef4444")
            else:
                label.config(text=("ON" if s else "OFF"),
                             fg="#10b981" if s else "#ef4444")

    def scene_good_morning(self):
        self._log("Activating Good Morning")
        self.set_device("light", True)
        self.set_device("fan", True)
        self.set_device("ac", False)
        self.set_device("door", True)

    def scene_good_night(self):
        self._log("Activating Good Night")
        self.set_device("light", False)
        self.set_device("fan", False)
        self.set_device("ac", True)
        self.set_device("door", False)

    def scene_away(self):
        self._log("Activating Away")
        for d in DEVICES:
            if d["id"] != "door":
                self.set_device(d["id"], False)
        self.set_device("door", False)

    def _process_queue(self):
        while not self.queue.empty():
            item = self.queue.get()
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            typ, payload = item[0], item[1]
            if typ == "transcript":
                self._log(f"Voice heard: {payload}")
            elif typ == "command":
                self._log(f"Executing voice command: {payload}")
                self._execute_canonical(payload)
            elif typ == "command_unknown":
                self._log(f"Unrecognized spoken command: {payload}")
                self.tts.speak("I heard: " + payload + ". Please repeat or try simpler command.")
            elif typ == "log":
                self._log(payload)
            elif typ == "wake":
                self._log("Wake-word detected")
                self.tts.speak("Yes?")
            else:
                self._log(f"Queue item: {typ} -> {payload}")

        self.master.after(150, self._process_queue)

    def report_status(self):
        parts = []
        for k, v in self.device_state.items():
            parts.append(f"{k}: {self._human_state(k)}")
        msg = " | ".join(parts)
        self._log(msg)
        self.tts.speak("Reporting status")

    def _toggle_voice(self):
        if not SR_AVAILABLE:
            messagebox.showwarning("Voice Disabled", "SpeechRecognition not installed. Typing mode works.")
            return
        if not self.voice_engine.running:
            val = self.mic_var.get()
            if val == "(default)":
                self.voice_engine.set_microphone(None)
            else:
                try:
                    idx = int(val)
                    self.voice_engine.set_microphone(idx)
                except Exception:
                    self.voice_engine.set_microphone(None)
            self.voice_engine.start()
            self.voice_btn.config(text="Stop Voice")
            self.status_var.set("Voice: Listening")
        else:
            self.voice_engine.stop()
            self.voice_btn.config(text="Start Voice")
            self.status_var.set("Ready")

    def _toggle_wake(self):
        if not self.wake_engine.running:
            self.wake_engine.start()
            self.wake_btn.config(text="Stop Wake-word")
            self.status_var.set("Wake-word: Active")
        else:
            self.wake_engine.stop()
            self.wake_btn.config(text="Start Wake-word")
            self.status_var.set("Ready")

    def _on_wake_detected(self):
        self.queue.put(("wake", True))
        if SR_AVAILABLE and not self.voice_engine.running:
            self.voice_engine.start()
        self.tts.speak("I'm listening")

    def _log(self, text):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.log_area.config(state="normal")
            self.log_area.insert("end", f"[{ts}] {text}\n")
            self.log_area.see("end")
            self.log_area.config(state="disabled")
        except Exception:
            pass
        print(f"LOG: {text}")

    def _set_ui_state(self, state):
        if state == "listening":
            self.status_var.set("Voice: Listening")
        elif state == "processing":
            self.status_var.set("Voice: Processing")
        elif state == "idle":
            self.status_var.set("Ready")
        elif state == "wake_detected":
            self.status_var.set("Wake-word detected")

    def show_help(self):
        examples = (
            "Examples:\n"
            "- Turn on the light\n"
            "- Turn off the fan\n"
            "- Lock the door\n"
            "- Unlock the door\n"
            "- Good morning / Good night\n"
            "- Away\n"
            "- Status\n\n"
            "(Voice features require SpeechRecognition and microphone)"
        )
        messagebox.showinfo("Help", examples)


if __name__ == "__main__":
    root = tk.Tk()
    app = SmartHomeApp(root)
    root.mainloop()