# 🏠 Smart Home Automation System with Voice Control

A Python-based Smart Home Automation System that enables users to control and monitor household devices through voice commands, wake-word activation, and a graphical user interface (GUI). The system integrates speech recognition, text-to-speech responses, smart automation scenes, and device state persistence to provide an interactive smart home experience.
---
## 📌 Project Description

This Smart Home Automation System is designed to simulate the functionality of modern smart homes by allowing users to control appliances through voice commands or manual controls.

The application features a desktop dashboard built using Tkinter, voice recognition using SpeechRecognition, text-to-speech responses using pyttsx3, wake-word detection, smart automation scenes, emergency mode functionality, and persistent storage of device states.

The system demonstrates practical applications of Python in automation, artificial intelligence, GUI development, and voice-based interaction.

---

## ✨ Features

### 🎤 Voice Control
- Control devices using voice commands
- Real-time speech recognition
- Fuzzy command matching for better accuracy

### 🔊 Voice Assistant
- Text-to-speech feedback
- Smart assistant greetings
- Spoken status reports

### 🎯 Wake Word Detection
- Wake assistant using:
  - "Hey Home"
- Automatic listening activation after wake-word detection

### 🖥️ Interactive GUI
- Device dashboard
- Device status indicators
- Manual ON/OFF controls
- Activity log panel
- Microphone selection support

### 🏠 Smart Home Devices
Supported devices:

- Living Room Light
- Ceiling Fan
- Air Conditioner
- Front Door Lock
- Heater

### 🌅 Smart Scenes

#### Good Morning Mode
- Light ON
- Fan ON
- AC OFF
- Door Unlocked

#### Good Night Mode
- Light OFF
- Fan OFF
- AC ON
- Door Locked

#### Away Mode
- Turns OFF all appliances
- Locks the front door

### 🚨 Emergency Mode
- Shuts down all non-essential devices
- Locks the house
- Displays emergency alert

### 💾 Data Persistence
- Saves device states automatically
- Loads previous states on startup
- JSON-based storage system

### 📋 Activity Logging
- Command history
- Device state changes
- Voice recognition logs
- Wake-word events

---

## 🛠️ Technologies Used

| Technology | Purpose |
|------------|----------|
| Python | Core Programming Language |
| Tkinter | GUI Development |
| SpeechRecognition | Voice Recognition |
| PyAudio | Microphone Access |
| pyttsx3 | Text-to-Speech |
| JSON | State Persistence |
| Threading | Background Processing |
| Difflib | Fuzzy Command Matching |
| Porcupine | Wake Word Detection |

---

## 🏗️ System Architecture

User Voice Input
↓
Wake Word Detection
↓
Speech Recognition
↓
Command Processing
↓
Device Controller
↓
GUI Update + Voice Feedback
↓
State Storage (JSON)

---

## 🎤 Supported Voice Commands

### Device Commands

- Turn on light
- Turn off light
- Turn on fan
- Turn off fan
- Turn on AC
- Turn off AC
- Turn on heater
- Turn off heater
- Lock door
- Unlock door

### Scene Commands

- Good morning
- Good night
- Away mode

### Utility Commands

- Status
- Emergency mode

---

## 📂 Project Structure

smart-home-automation/

├── smart_home_finalminiproject.py

├── sh_state.json

├── README.md

└── requirements.txt

```bash
git clone https://github.com/yourusername/smart-home-automation.git
