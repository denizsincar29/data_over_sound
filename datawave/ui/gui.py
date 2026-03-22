"""
wxPython GUI entry point for DataWave.
"""

import wx
import threading
import time
import os
import sounddevice as sd
from datawave.core.dispatcher import ProtocolDispatcher
from datawave.utils.settings import settings
from datawave.utils.screen_reader import screen_reader
from datawave.utils.parser import extract_info
from datawave.services.file_transfer import FileTransferProtocol

class MainFrame(wx.Frame):
    def __init__(self, parent, title):
        super(MainFrame, self).__init__(parent, title=title, size=(600, 500))

        self.dispatcher = ProtocolDispatcher(self.Log, self.UpdateProgress)
        self.InitUI()
        self.SetupHotkeys()

        # Timer for periodic checks (timeouts)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(1000)

    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Volume Slider
        hbox_vol = wx.BoxSizer(wx.HORIZONTAL)
        hbox_vol.Add(wx.StaticText(panel, label="Volume:"), flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
        self.vol_slider = wx.Slider(panel, value=settings.get("volume", 50), minValue=0, maxValue=100, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.vol_slider.Bind(wx.EVT_SLIDER, self.OnVolumeChange)
        hbox_vol.Add(self.vol_slider, proportion=1, flag=wx.EXPAND)
        vbox.Add(hbox_vol, flag=wx.EXPAND | wx.ALL, border=5)

        # Message History
        self.history = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        vbox.Add(self.history, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

        # Progress bar
        self.progress = wx.Gauge(panel, range=100)
        vbox.Add(self.progress, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=5)
        self.progress.Hide()

        # Input Area
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.input_text = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.input_text.Bind(wx.EVT_TEXT_ENTER, self.OnSend)
        hbox.Add(self.input_text, proportion=1, flag=wx.EXPAND)

        send_btn = wx.Button(panel, label='Send')
        send_btn.Bind(wx.EVT_BUTTON, self.OnSend)
        hbox.Add(send_btn, flag=wx.LEFT, border=5)

        file_btn = wx.Button(panel, label='Send File')
        file_btn.Bind(wx.EVT_BUTTON, self.OnSendFile)
        hbox.Add(file_btn, flag=wx.LEFT, border=5)

        vbox.Add(hbox, flag=wx.EXPAND | wx.ALL, border=5)
        panel.SetSizer(vbox)

        # Menu Bar
        self.menubar = wx.MenuBar()

        # File Menu
        fileMenu = wx.Menu()
        sendFileItem = fileMenu.Append(wx.ID_ANY, 'Send File...\tCtrl+O', 'Select a file to send')
        self.Bind(wx.EVT_MENU, self.OnSendFile, sendFileItem)
        openItem = fileMenu.Append(wx.ID_ANY, 'Open Received...', 'Parse and open URLs/Emails/Phones')
        self.Bind(wx.EVT_MENU, self.OnOpenReceived, openItem)
        fileMenu.AppendSeparator()
        exitItem = fileMenu.Append(wx.ID_EXIT, 'Exit', 'Exit application')
        self.Bind(wx.EVT_MENU, self.OnExit, exitItem)
        self.menubar.Append(fileMenu, '&File')

        # Protocol Menu
        protocolMenu = wx.Menu()
        protocolItem = protocolMenu.Append(wx.ID_ANY, 'Select Protocol...', 'Choose encoding protocol')
        self.Bind(wx.EVT_MENU, self.OnProtocolDialog, protocolItem)
        self.menubar.Append(protocolMenu, '&Protocol')

        # Remote Menu
        self.remoteMenu = wx.Menu()
        self.UpdateRemoteMenu()
        self.menubar.Append(self.remoteMenu, '&Remote')

        # Settings Menu
        settingsMenu = wx.Menu()

        # Device submenus
        devices = sd.query_devices()
        inputMenu = wx.Menu()
        outputMenu = wx.Menu()

        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                item = inputMenu.Append(wx.ID_ANY, d['name'], kind=wx.ITEM_RADIO)
                if i == settings.get("devices")[0]: item.Check()
                self.Bind(wx.EVT_MENU, lambda evt, idx=i: self.OnSelectDevice(0, idx), item)

            if d['max_output_channels'] > 0:
                item = outputMenu.Append(wx.ID_ANY, d['name'], kind=wx.ITEM_RADIO)
                if i == settings.get("devices")[1]: item.Check()
                self.Bind(wx.EVT_MENU, lambda evt, idx=i: self.OnSelectDevice(1, idx), item)

        settingsMenu.AppendSubMenu(inputMenu, 'Input Device')
        settingsMenu.AppendSubMenu(outputMenu, 'Output Device')

        settingsMenu.AppendSeparator()
        remoteEnableItem = settingsMenu.Append(wx.ID_ANY, 'Enable Remote Commands', kind=wx.ITEM_CHECK)
        remoteEnableItem.Check(settings.get("enable_remote_commands", False))
        self.Bind(wx.EVT_MENU, self.OnToggleRemoteCommands, remoteEnableItem)

        # Advanced Settings Submenu
        advMenu = wx.Menu()
        sarItem = advMenu.Append(wx.ID_ANY, 'Set SAR Delay...')
        self.Bind(wx.EVT_MENU, lambda evt: self.OnSetDelay("sar_delay", "SAR Delay (ms)"), sarItem)
        subItem = advMenu.Append(wx.ID_ANY, 'Set Subsequent Delay...')
        self.Bind(wx.EVT_MENU, lambda evt: self.OnSetDelay("subsequent_delay", "Subsequent Delay (ms)"), subItem)

        settingsMenu.AppendSubMenu(advMenu, 'Advanced')

        self.menubar.Append(settingsMenu, '&Settings')
        self.SetMenuBar(self.menubar)
        self.Show()

    def UpdateRemoteMenu(self):
        # Clear existing items
        for item in self.remoteMenu.GetMenuItems():
            self.remoteMenu.DestroyItem(item)

        for cmd_name in self.dispatcher.remote_control.commands:
            item = self.remoteMenu.Append(wx.ID_ANY, f"Execute {cmd_name}")
            self.Bind(wx.EVT_MENU, lambda evt, name=cmd_name: self.OnSendRemoteCommand(name), item)

        self.remoteMenu.AppendSeparator()
        queryItem = self.remoteMenu.Append(wx.ID_ANY, "Query Remote Functions")
        self.Bind(wx.EVT_MENU, self.dispatcher.query_remote, queryItem)

        saveWavItem = self.remoteMenu.Append(wx.ID_ANY, "Save Remote Sounds to WAV")
        self.Bind(wx.EVT_MENU, self.OnSaveRemoteSounds, saveWavItem)

    def OnSend(self, event):
        msg = self.input_text.GetValue()
        if msg:
            self.dispatcher.send_text(msg)
            self.Log(f"Me: {msg}")
            self.input_text.Clear()

    def OnSendFile(self, event):
        with wx.FileDialog(self, "Open file", wildcard="*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL: return
            path = fileDialog.GetPath()

        threading.Thread(target=self.dispatcher.send_file, args=(path,), daemon=True).start()

    def OnSendRemoteCommand(self, cmd_name):
        args = ""
        if cmd_name == "open_url":
            dlg = wx.TextEntryDialog(self, "Enter URL:", "Command Arguments")
            if dlg.ShowModal() == wx.ID_OK: args = dlg.GetValue()
            dlg.Destroy()
            if not args: return
        self.dispatcher.send_remote_command(cmd_name, args)

    def OnProtocolDialog(self, event):
        # Placeholder for complex protocol dialog
        pass

    def OnVolumeChange(self, event):
        val = self.vol_slider.GetValue()
        settings.set("volume", val)

    def OnToggleRemoteCommands(self, event):
        settings.set("enable_remote_commands", event.IsChecked())

    def OnSetDelay(self, key, label):
        current = settings.get(key, 500 if "sar" in key else 100)
        dlg = wx.TextEntryDialog(self, f"Enter {label}:", "Advanced Settings", str(current))
        if dlg.ShowModal() == wx.ID_OK:
            try:
                val = int(dlg.GetValue())
                settings.set(key, val)
            except ValueError:
                wx.MessageBox("Invalid value. Please enter an integer.", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def OnSaveRemoteSounds(self, event):
        msg = self.dispatcher.save_remote_sounds_to_wav()
        wx.MessageBox(msg, "Save Remote Sounds", wx.OK | wx.ICON_INFORMATION)

    def OnSelectDevice(self, type, idx):
        devs = settings.get("devices")
        devs[type] = idx
        settings.set("devices", devs)
        self.Log("Restart required to apply device changes.")

    def OnTimer(self, event):
        self.dispatcher.check_timeouts()

    def OnOpenReceived(self, event):
        # Result of last parsing...
        pass

    def Log(self, msg):
        wx.CallAfter(self.history.AppendText, f"{msg}\n")
        screen_reader.speak(msg)

    def UpdateProgress(self, value, max_value):
        wx.CallAfter(self._UpdateProgressUI, value, max_value)

    def _UpdateProgressUI(self, value, max_value):
        if value < max_value:
            self.progress.Show()
            self.progress.SetRange(max_value)
            self.progress.SetValue(value)
        else:
            self.progress.Hide()
        self.Layout()

    def SetupHotkeys(self):
        # Hotkey logic from settings
        pass

    def OnExit(self, event):
        self.dispatcher.stop()
        self.Close(True)

def main():
    app = wx.App()
    MainFrame(None, title='DataWave GUI')
    app.MainLoop()

if __name__ == "__main__":
    main()
