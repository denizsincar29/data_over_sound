import wx
import gw
import os
import time
import threading
from file_sharing import FileSender, FileReceiver, try_to_utf8
from command_validator import CommandValidator
from settings_manager import settings
from screen_reader_manager import screen_reader
from command_manager import command_manager, AppAPI
import sounddevice as sd

class MainFrame(wx.Frame):
    def __init__(self, parent, title):
        super(MainFrame, self).__init__(parent, title=title, size=(600, 500))
        
        self.output_handler = GUIOutputHandler(self)
        self.gw = gw.GW(self.output_handler.data_callback)
        self.output_handler.set_gw(self.gw)
        
        # Update command_manager's API
        api = AppAPI(self.gw, self.Log)
        command_manager.set_api(api)

        self.query_active = False
        self.query_functions = []
        self.query_last_received = 0

        self.InitUI()
        self.gw.start()
        self.SetupHotkeys()

        # Timer for protocol timeouts (NACK)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(1000) # Check every second

    def InitUI(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

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

        self.remoteProtocolItem = settingsMenu.Append(wx.ID_ANY, 'Send Protocol Change Command', kind=wx.ITEM_CHECK)
        self.remoteProtocolItem.Check(settings.get("enable_remote_protocol_change", True))
        self.Bind(wx.EVT_MENU, self.OnToggleRemoteProtocol, self.remoteProtocolItem)

        self.receiveRemoteCommandsItem = settingsMenu.Append(wx.ID_ANY, 'Receive Remote Commands', kind=wx.ITEM_CHECK)
        self.receiveRemoteCommandsItem.Check(settings.get("enable_remote_commands", False))
        self.Bind(wx.EVT_MENU, self.OnToggleReceiveRemoteCommands, self.receiveRemoteCommandsItem)

        # Device submenus
        devices = sd.query_devices()
        inputMenu = wx.Menu()
        outputMenu = wx.Menu()

        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                item = inputMenu.Append(wx.ID_ANY, d['name'], kind=wx.ITEM_RADIO)
                if i == settings.get("devices")[0]:
                    item.Check()
                self.Bind(wx.EVT_MENU, lambda evt, idx=i: self.OnSelectDevice(0, idx), item)

            if d['max_output_channels'] > 0:
                item = outputMenu.Append(wx.ID_ANY, d['name'], kind=wx.ITEM_RADIO)
                if i == settings.get("devices")[1]:
                    item.Check()
                self.Bind(wx.EVT_MENU, lambda evt, idx=i: self.OnSelectDevice(1, idx), item)

        settingsMenu.AppendSubMenu(inputMenu, 'Input Device')
        settingsMenu.AppendSubMenu(outputMenu, 'Output Device')

        testDeviceItem = settingsMenu.Append(wx.ID_ANY, 'Test Device', 'Test selected audio devices')
        self.Bind(wx.EVT_MENU, self.OnTestDevice, testDeviceItem)

        settingsMenu.AppendSeparator()

        resetItem = settingsMenu.Append(wx.ID_ANY, 'Reset Instance', 'Reset ggwave instance')
        self.Bind(wx.EVT_MENU, self.OnReset, resetItem)
        self.menubar.Append(settingsMenu, '&Settings')

        self.SetMenuBar(self.menubar)
        self.Show()

    def UpdateRemoteMenu(self):
        # Clear existing items
        for item in self.remoteMenu.GetMenuItems():
            self.remoteMenu.DestroyItem(item)

        # Dynamic commands
        for cmd_name in command_manager.commands:
            item = self.remoteMenu.Append(wx.ID_ANY, f"Execute {cmd_name}", f"Send {cmd_name} command")
            self.Bind(wx.EVT_MENU, lambda evt, name=cmd_name: self.OnSendRemoteCommand(name), item)

        self.remoteMenu.AppendSeparator()

        createPluginItem = self.remoteMenu.Append(wx.ID_ANY, "Create New Command...", "Create a template for a new plugin")
        self.Bind(wx.EVT_MENU, self.OnCreatePlugin, createPluginItem)

        refreshItem = self.remoteMenu.Append(wx.ID_ANY, "Refresh Local Commands", "Reload local plugins and refresh list")
        self.Bind(wx.EVT_MENU, self.OnRefreshLocalCommands, refreshItem)

        queryItem = self.remoteMenu.Append(wx.ID_ANY, "Query Remote Functions", "Ask remote device for its available commands")
        self.Bind(wx.EVT_MENU, self.OnQueryRemoteFunctions, queryItem)

        self.remoteMenu.AppendSeparator()

        hotkeyItem = self.remoteMenu.Append(wx.ID_ANY, "Assign Hotkeys...", "Assign hotkeys to remote commands")
        self.Bind(wx.EVT_MENU, self.OnAssignHotkeys, hotkeyItem)

    def OnCreatePlugin(self, event):
        dlg = wx.TextEntryDialog(self, "Enter name for new plugin folder:", "Create Plugin")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name:
                success, msg = command_manager.create_plugin_template(name)
                wx.MessageBox(msg, "Create Plugin", wx.OK | (wx.ICON_INFORMATION if success else wx.ICON_ERROR))
                if success:
                    self.UpdateRemoteMenu()
        dlg.Destroy()

    def OnRefreshLocalCommands(self, event):
        command_manager.load_plugins()
        self.UpdateRemoteMenu()
        self.Log("Local commands refreshed.")

    def OnQueryRemoteFunctions(self, event):
        self.Log("Querying remote device for functions...")
        self.gw.send("__QUERY_REMOTE__")
        # Initialize query tracking
        self.query_last_received = time.time()
        self.query_active = True
        self.query_functions = []

    def OnSelectProtocol(self, protocol, payload_length=-1, broadcast=True):
        if broadcast and self.remoteProtocolItem.IsChecked():
            # Send command before changing local protocol
            cmd = f"__RPC__:{protocol}:{payload_length}"
            self.gw.send(cmd)
            self.Log(f"Sent remote protocol change: {protocol}:{payload_length}")
            time.sleep(1) # Give it some time to send

        self.gw.protocol = protocol
        settings.set("protocol", protocol)
        settings.set("payload_length", payload_length)
        self.gw.switchinstance(payload_length)
        self.Log(f"Protocol set to {protocol} (Payload: {payload_length if payload_length != -1 else 'Default'})")

    def OnToggleRemoteProtocol(self, event):
        settings.set("enable_remote_protocol_change", self.remoteProtocolItem.IsChecked())

    def OnToggleReceiveRemoteCommands(self, event):
        settings.set("enable_remote_commands", self.receiveRemoteCommandsItem.IsChecked())

    def OnSendRemoteCommand(self, cmd_name):
        # In a real scenario, we might want to ask for arguments
        args = ""
        if cmd_name == "open_url":
            dlg = wx.TextEntryDialog(self, "Enter URL:", "Command Arguments")
            if dlg.ShowModal() == wx.ID_OK:
                args = dlg.GetValue()
            dlg.Destroy()
            if not args: return

        cmd = f"__REMOTE__:{cmd_name}:{args}"
        self.gw.send(cmd)
        self.Log(f"Sent remote command: {cmd_name} {args}")

    def OnAssignHotkeys(self, event):
        dlg = wx.Dialog(self, title="Assign Hotkeys")
        vbox = wx.BoxSizer(wx.VERTICAL)

        current_hotkeys = settings.get("hotkeys", {})
        hotkey_inputs = {}

        for cmd_name in command_manager.commands:
            hbox = wx.BoxSizer(wx.HORIZONTAL)
            hbox.Add(wx.StaticText(dlg, label=f"{cmd_name}:"), proportion=1)
            ctrl = wx.TextCtrl(dlg, value=current_hotkeys.get(cmd_name, ""))
            hbox.Add(ctrl, proportion=2)
            hotkey_inputs[cmd_name] = ctrl
            vbox.Add(hbox, flag=wx.EXPAND | wx.ALL, border=5)

        btn_box = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(dlg, wx.ID_OK)
        cancel_btn = wx.Button(dlg, wx.ID_CANCEL)
        btn_box.Add(ok_btn)
        btn_box.Add(cancel_btn, flag=wx.LEFT, border=5)
        vbox.Add(btn_box, flag=wx.ALIGN_CENTER | wx.ALL, border=10)

        dlg.SetSizer(vbox)
        vbox.Fit(dlg)

        if dlg.ShowModal() == wx.ID_OK:
            new_hotkeys = {name: ctrl.GetValue() for name, ctrl in hotkey_inputs.items() if ctrl.GetValue()}
            settings.set("hotkeys", new_hotkeys)
            self.Log("Hotkeys updated. Please restart app to apply.")
        dlg.Destroy()

    def OnProtocolDialog(self, event):
        protocols = [
            "0: DT, Mid, No ECC, Slowest",
            "1: DT, Mid, No ECC, Normal",
            "2: DT, Mid, No ECC, Fastest",
            "3: DT, Ultra, No ECC, Slowest",
            "4: DT, Ultra, No ECC, Normal",
            "5: DT, Ultra, No ECC, Fastest",
            "6: DT, Low, ECC, Slowest",
            "7: DT, Low, ECC, Normal",
            "8: DT, Low, ECC, Fastest",
            "9: ST, ECC, Slowest",
            "10: ST, ECC, Normal",
            "11: ST, ECC, Fastest",
        ]

        dlg = wx.Dialog(self, title="Select Protocol")
        vbox = wx.BoxSizer(wx.VERTICAL)

        vbox.Add(wx.StaticText(dlg, label="Choose Protocol:"), flag=wx.ALL, border=5)
        self.protocol_list = wx.ListBox(dlg, choices=protocols, size=(250, 150))
        self.protocol_list.SetSelection(self.gw.protocol)
        vbox.Add(self.protocol_list, flag=wx.EXPAND | wx.ALL, border=5)

        self.payload_checkbox = wx.CheckBox(dlg, label="Specify payload length")
        initial_payload = settings.get("payload_length", -1)
        self.payload_checkbox.SetValue(initial_payload != -1)
        vbox.Add(self.payload_checkbox, flag=wx.ALL, border=5)

        self.payload_label = wx.StaticText(dlg, label="Payload Length (4-64):")
        vbox.Add(self.payload_label, flag=wx.LEFT | wx.RIGHT | wx.TOP, border=5)
        self.payload_box = wx.TextCtrl(dlg, value=str(initial_payload if initial_payload != -1 else 32))
        vbox.Add(self.payload_box, flag=wx.EXPAND | wx.ALL, border=5)

        def UpdateUI(protocol_idx):
            is_st = protocol_idx >= 9
            if is_st:
                self.payload_checkbox.SetValue(True)
                self.payload_checkbox.Hide()
                self.payload_label.Show()
                self.payload_box.Show()
                self.payload_box.SetValue("32")
                self.payload_box.Disable()
            else:
                self.payload_checkbox.Show()
                self.payload_box.Enable()
                if self.payload_checkbox.IsChecked():
                    self.payload_label.Show()
                    self.payload_box.Show()
                else:
                    self.payload_label.Hide()
                    self.payload_box.Hide()
            dlg.Layout()
            vbox.Fit(dlg)

        self.protocol_list.Bind(wx.EVT_LISTBOX, lambda e: UpdateUI(self.protocol_list.GetSelection()))
        self.payload_checkbox.Bind(wx.EVT_CHECKBOX, lambda e: UpdateUI(self.protocol_list.GetSelection()))

        UpdateUI(self.protocol_list.GetSelection())

        btn_box = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(dlg, wx.ID_OK)
        cancel_btn = wx.Button(dlg, wx.ID_CANCEL)
        btn_box.Add(ok_btn)
        btn_box.Add(cancel_btn, flag=wx.LEFT, border=5)
        vbox.Add(btn_box, flag=wx.ALIGN_CENTER | wx.ALL, border=10)

        dlg.SetSizer(vbox)
        vbox.Fit(dlg)

        if dlg.ShowModal() == wx.ID_OK:
            protocol = self.protocol_list.GetSelection()
            try:
                if self.payload_checkbox.IsChecked():
                    payload = int(self.payload_box.GetValue())
                    if payload < 4 or payload > 64:
                        wx.MessageBox("Payload length must be 4-64", "Error", wx.OK | wx.ICON_ERROR)
                        return
                else:
                    payload = -1
                self.OnSelectProtocol(protocol, payload)
            except ValueError:
                wx.MessageBox("Invalid payload length", "Error", wx.OK | wx.ICON_ERROR)

        dlg.Destroy()

    def OnSelectDevice(self, type, idx):
        devs = settings.get("devices")
        devs[type] = idx
        settings.set("devices", devs)
        self.Log(f"{'Input' if type == 0 else 'Output'} device set to index {idx}")
        # Need to restart GW to apply device changes
        self.Log("Restarting audio stream...")
        self.gw.stop()
        import configure_sound_devices
        configure_sound_devices.devs = devs
        self.gw = gw.GW(self.output_handler.data_callback)
        # Update output handler with new GW instance
        self.output_handler.set_gw(self.gw)
        # Re-attach the receiver and sender to the NEW GW instance
        if self.output_handler.receiver:
            self.output_handler.receiver.gw = self.gw
        if self.output_handler.sender:
            self.output_handler.sender.gw = self.gw
        self.gw.start()

    def OnTestDevice(self, event):
        def _run_test():
            wx.CallAfter(self.Log, "Testing output (2s sine wave)...")
            context = configure_sound_devices.DeviceTestContext()
            devs = settings.get("devices")
            out_dev = devs[1] if devs[1] != -1 else None
            in_dev = devs[0] if devs[0] != -1 else None

            try:
                with sd.OutputStream(
                    device=out_dev,
                    channels=1,
                    callback=context.sinecallback,
                    samplerate=48000
                ):
                    time.sleep(2)
            except Exception as e:
                wx.CallAfter(self.Log, f"Output test failed: {e}")
                return

            wx.CallAfter(self.Log, "Testing input (5s microphone echo)...")
            try:
                with sd.Stream(
                    device=(in_dev, out_dev),
                    channels=1,
                    callback=context.incallback,
                    samplerate=48000
                ):
                    time.sleep(5)
            except Exception as e:
                wx.CallAfter(self.Log, f"Input test failed: {e}")
                return

            wx.CallAfter(self.Log, "Device test completed.")

        threading.Thread(target=_run_test, daemon=True).start()

    def OnReset(self, event):
        self.gw.switchinstance(-1)
        self.Log("Instance reset")

    def OnTimer(self, event):
        res = self.output_handler.receiver.check_timeout()
        if res == "SENT_NACK":
            self.Log(f"Still waiting for chunks of {self.output_handler.receiver.filename}. Sent NACK.")

        if self.query_active:
            if time.time() - self.query_last_received > 30:
                self.query_active = False
                self.Log(f"Remote query timed out. Received: {', '.join(self.query_functions)}")

    def OnOpenReceived(self, event):
        from webbrowser import open as wopen
        import parse

        result = parse.extract_info(self.output_handler.data)
        items_to_open = []
        if result["urls"]: items_to_open.extend([f"URL: {url}" for url in result["urls"]])
        if result["emails"]: items_to_open.extend([f"Email: {email}" for email in result["emails"]])
        if result["phones"]: items_to_open.extend([f"Phone: {phone}" for phone in result["phones"]])

        if not items_to_open:
            wx.MessageBox("No URLs, emails, or phone numbers found to open", "No data", wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.MessageDialog(self, "The following items will be opened:\n" + "\n".join(items_to_open),
                               "Confirm Open", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            for url in result["urls"]: wopen(url)
            for email in result["emails"]: wopen(f"mailto:{email}")
            for phone in result["phones"]: wopen(f"tel:{phone}")
        dlg.Destroy()

    def OnSend(self, event):
        msg = self.input_text.GetValue()
        if msg:
            if msg.startswith("/"):
                # Handle CLI commands in GUI?
                self.Log("Commands are not fully supported in GUI yet. Use menus.")
            else:
                self.gw.send(msg)
                self.Log(f"Me: {msg}")
            self.input_text.Clear()

    def OnSendFile(self, event):
        with wx.FileDialog(self, "Open file", wildcard="*.*",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            path = fileDialog.GetPath()

        threading.Thread(target=self._SendFileThread, args=(path,), daemon=True).start()

    def _SendFileThread(self, path):
        sender = FileSender(self.gw, path)
        self.output_handler.sender = sender
        wx.CallAfter(self.Log, f"Starting handshake for {sender.filename}...")
        sender.send_handshake()

        # Wait for ready signal (30s timeout)
        start_time = time.time()
        while sender.state == "WAITING_FOR_READY" and time.time() - start_time < 30:
            time.sleep(0.1)

        if sender.state == "WAITING_FOR_READY":
            self.output_handler.sender = None
            wx.CallAfter(self.Log, "Handshake timeout (30s).")
            return

        wx.CallAfter(self.Log, "Handshake successful, sending chunks...")

        # Wait for completion or retransmission requests
        start_time = time.time()
        while sender.state == "WAITING_FOR_ACK" and time.time() - start_time < 60:
            time.sleep(0.1)

        if sender.state == "DONE":
            wx.CallAfter(self.Log, f"File {sender.filename} sent successfully.")
        else:
            wx.CallAfter(self.Log, f"File transfer timed out or failed. State: {sender.state}")
        self.output_handler.sender = None

    def SetupHotkeys(self):
        hotkeys = settings.get("hotkeys", {})
        accel_entries = []
        self.hotkey_map = {}
        for cmd_name, hotkey_str in hotkeys.items():
            if not hotkey_str: continue
            parts = hotkey_str.split('+')
            flags = wx.ACCEL_NORMAL
            key = None
            for p in parts:
                p = p.strip().upper()
                if p == "CTRL": flags |= wx.ACCEL_CTRL
                elif p == "SHIFT": flags |= wx.ACCEL_SHIFT
                elif p == "ALT": flags |= wx.ACCEL_ALT
                elif len(p) == 1: key = ord(p)
                # handle F1-F12 if needed

            if key:
                vid = wx.NewIdRef()
                accel_entries.append(wx.AcceleratorEntry(flags, key, vid))
                self.Bind(wx.EVT_MENU, lambda evt, name=cmd_name: self.OnSendRemoteCommand(name), id=vid)

        if accel_entries:
            self.SetAcceleratorTable(wx.AcceleratorTable(accel_entries))

    def Log(self, msg):
        self.history.AppendText(msg + "\n")
        screen_reader.speak(msg)

    def UpdateProgress(self, value, max_value):
        if value < max_value:
            self.progress.Show()
            self.progress.SetRange(max_value)
            self.progress.SetValue(value)
        else:
            self.progress.Hide()
        self.Layout()

    def OnExit(self, event):
        self.gw.stop()
        self.Close(True)

class GUIOutputHandler:
    def __init__(self, frame):
        self.frame = frame
        self.receiver = None
        self.sender = None
        self.gw = None
        self.data = ""

    def set_gw(self, gw_instance):
        self.gw = gw_instance
        self.receiver = FileReceiver(self.gw)

    def data_callback(self, data):
        # Handle remote control command
        text = try_to_utf8(data)

        if text == "__QUERY_REMOTE__":
            if not settings.get("enable_remote_commands", False):
                return
            def respond():
                funcs = command_manager.get_remote_functions()
                for f in funcs:
                    self.gw.send(f)
                    time.sleep(1)
                self.gw.send("$EOF")
            threading.Thread(target=respond, daemon=True).start()
            return

        if self.frame.query_active:
            if text == "$EOF":
                self.frame.query_active = False
                wx.CallAfter(self.frame.Log, f"Remote functions received: {', '.join(self.frame.query_functions)}")
            else:
                self.frame.query_functions.append(text)
                self.frame.query_last_received = time.time() # Reset timeout
                wx.CallAfter(self.frame.Log, f"Remote function: {text}")
            return

        if text.startswith("__REMOTE__:"):
            if not settings.get("enable_remote_commands", False):
                wx.CallAfter(self.frame.Log, "Received remote command, but feature is disabled in settings.")
                return
            try:
                parts = text.split(":")
                cmd_name = parts[1]
                args = parts[2] if len(parts) > 2 else ""
                wx.CallAfter(self.frame.Log, f"Executing Remote Command: {cmd_name} {args}")
                result = command_manager.execute(cmd_name, *([args] if args else []))
                wx.CallAfter(self.frame.Log, f"Command Result: {result}")
                return
            except (ValueError, IndexError) as e:
                wx.CallAfter(self.frame.Log, f"Error parsing remote command: {e}")
                return

        # Handle remote protocol change command
        if text.startswith("__RPC__:"):
            try:
                parts = text.split(":")
                protocol = int(parts[1])
                payload = int(parts[2])
                wx.CallAfter(self.frame.Log, f"Received Remote Protocol Change: Protocol {protocol}, Payload {payload}")
                wx.CallAfter(self.frame.OnSelectProtocol, protocol, payload, broadcast=False)
                return
            except (ValueError, IndexError):
                pass

        # Handle sender state
        if self.sender and self.sender.state != "DONE":
            if self.sender.handle_response(data):
                return

        # Handle receiver state
        if self.receiver:
            res = self.receiver.handle_data(data)
            if res:
                if res == "HANDSHAKE_RECEIVED":
                    wx.CallAfter(self.frame.Log, f"Receiving file: {self.receiver.filename} ({self.receiver.num_chunks} chunks)")
                    wx.CallAfter(self.frame.UpdateProgress, 0, self.receiver.num_chunks)
                elif res == "CHUNK_RECEIVED":
                    wx.CallAfter(self.frame.UpdateProgress, len(self.receiver.received_chunks), self.receiver.num_chunks)
                elif res == "SUCCESS":
                    wx.CallAfter(self.frame.Log, f"File received successfully: {self.receiver.filename}")
                    wx.CallAfter(self.frame.UpdateProgress, self.receiver.num_chunks, self.receiver.num_chunks)
                    self.receiver.reset()
                return

        text = try_to_utf8(data)
        self.data = text
        wx.CallAfter(self.frame.Log, text)

if __name__ == "__main__":
    app = wx.App()
    MainFrame(None, title='Data Over Sound')
    app.MainLoop()
