"""
Sound device configuration module.

Handles testing and selection of audio input/output devices.
"""

from os.path import exists
import json
import numpy as np
import sounddevice as sd
from settings_manager import settings

# Default device configuration
devs = settings.get("devices", [-1, -1])

# Audio parameters for device testing
_SAMPLERATE = 44100
_AMPLITUDE = 0.2
_FREQUENCY = 440


class DeviceTestContext:
    """Context for device testing to avoid global state."""
    
    def __init__(self):
        self.start_idx = 0
        self.samplerate = _SAMPLERATE
    
    def incallback(self, indata, outdata, frames, time, status):
        """Callback for input device testing (echo)."""
        if status:
            print(status)
        outdata[:] = indata
    
    def sinecallback(self, outdata, frames, time, status):
        """Callback for output device testing (sine wave)."""
        if status:
            print(status)
        t = (self.start_idx + np.arange(frames)) / self.samplerate
        t = t.reshape(-1, 1)
        outdata[:] = _AMPLITUDE * np.sin(2 * np.pi * _FREQUENCY * t)
        self.start_idx += frames


def testoutput():
    """Test and select output audio device."""
    context = DeviceTestContext()
    devices = sd.query_devices()
    
    while True:
        for d in devices:
            if d["max_output_channels"] == 0:
                continue
            context.samplerate = d["default_samplerate"]
            try:
                with sd.OutputStream(
                    device=d["index"],
                    channels=1,
                    callback=context.sinecallback,
                    samplerate=context.samplerate,
                ):
                    response = input(
                        f"This is {d['name']} playing sound. "
                        "If you prefer this device, and you hear the sound, "
                        "type y, otherwise just press enter: "
                    )
                    if "y" in response.lower():
                        return d["index"]
            except KeyboardInterrupt:
                exit()
            except Exception as e:
                print(f"Error opening {d['name']}: {e}")
                input("Press enter to continue")
        input("No sound device selected. Press enter to loop over")


def testinput(output_device_index):
    """
    Test and select input audio device.
    
    Args:
        output_device_index: Index of output device to use for echo test
    """
    print(
        "\nNow testing your microphone or other input device. "
        "After you press enter, we will go through all input devices "
        "and choose a device for you. While testing, you will hear your "
        "microphone or other device. If you don't hear it, just skip it."
    )
    input("Press enter to start")
    
    context = DeviceTestContext()
    devices = sd.query_devices()
    
    while True:
        for d in devices:
            if d["max_input_channels"] == 0:
                continue
            context.samplerate = d["default_samplerate"]
            try:
                with sd.Stream(
                    device=(d["index"], output_device_index),
                    channels=1,
                    callback=context.incallback,
                    samplerate=context.samplerate,
                ):
                    response = input(
                        f"This is {d['name']} playing sound. "
                        "If you prefer this device, and you hear the sound, "
                        "type y, otherwise just press enter: "
                    )
                    if "y" in response.lower():
                        return d["index"]
            except KeyboardInterrupt:
                exit()
            except Exception as e:
                print(f"Error opening {d['name']}: {e}")
                input("Press enter to continue")
        input("No sound device selected. Press enter to loop over")


def test():
    """Run device testing and save configuration."""
    global devs
    devs[1] = testoutput()
    devs[0] = testinput(devs[1])
    settings.set("devices", devs)


def load_devices():
    """Load device configuration from settings."""
    global devs
    devs = settings.get("devices", [-1, -1])


# Only run device configuration if this module is imported
# (not when testing or importing for other purposes)
# But only if devices are not already set
if devs != [-1, -1]:
    load_devices()
