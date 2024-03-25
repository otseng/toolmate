from freegenius import config
from freegenius import print1, print2, print3
from freegenius.utils.install import installmodule
from freegenius.utils.shared_utils import SharedUtil
import os

# For more information, read https://github.com/Uberi/speech_recognition#pyaudio-for-microphone-users

try:
    import sounddevice
    import speech_recognition as sr
    mic = sr.Microphone() 
    del mic
    config.pyaudioInstalled = True
except:
    if config.isTermux:
        config.pyaudioInstalled = False
        #print2("Installing 'portaudio' and 'Pyaudio' ...")
        #os.system("pkg install portaudio")
        #config.pyaudioInstalled = True if installmodule("--upgrade PyAudio") else False
    elif SharedUtil.isPackageInstalled("apt"):
        print2("Installing 'portaudio19-dev' and 'Pyaudio' ...")
        os.system("sudo apt update && sudo apt install portaudio19-dev")
        config.pyaudioInstalled = True if installmodule("--upgrade PyAudio") else False
    elif SharedUtil.isPackageInstalled("dnf"):
        print2("Installing 'portaudio-devel' and 'Pyaudio' ...")
        os.system("sudo dnf update && sudo dnf install portaudio-devel")
        config.pyaudioInstalled = True if installmodule("--upgrade PyAudio") else False
    elif SharedUtil.isPackageInstalled("brew"):
        print2("Installing 'portaudio' and 'Pyaudio' ...")
        os.system("brew install portaudio")
        config.pyaudioInstalled = True if installmodule("--upgrade PyAudio") else False
    else:
        config.pyaudioInstalled = False

if not config.pyaudioInstalled:
    print3("Note: 'ffmpeg' is not installed.")
    print1("It is essential for built-in voice typing feature.")