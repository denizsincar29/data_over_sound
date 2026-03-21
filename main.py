import wx
import gw
import os
import time
import threading
from file_sharing import FileSender, FileReceiver, try_to_utf8
from command_validator import CommandValidator

class MainFrame(wx.Frame):
    def __init__(self, parent, title):
        super(MainFrame, self).__init__(parent, title=title, size=(600, 500))
        
        self.output_handler = GUIOutputHandler(self)
        self.gw = gw.GW(self.output_handler.data_callback)
        self.output_handler.set_gw(self.gw)
        
        self.InitUI()
        self.gw.start()

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
        menubar = wx.MenuBar()

        # File Menu
        fileMenu = wx.Menu()
        openItem = fileMenu.Append(wx.ID_ANY, 'Open Received...', 'Parse and open URLs/Emails/Phones')
        self.Bind(wx.EVT_MENU, self.OnOpenReceived, openItem)
        exitItem = fileMenu.Append(wx.ID_EXIT, 'Exit', 'Exit application')
        self.Bind(wx.EVT_MENU, self.OnExit, exitItem)
        menubar.Append(fileMenu, '&File')

        # Protocol Menu
        protocolMenu = wx.Menu()
        for i in range(12):
            item = protocolMenu.Append(wx.ID_ANY, f'Protocol {i}', f'Switch to protocol {i}', kind=wx.ITEM_RADIO)
            if i == self.gw.protocol:
                item.Check()
            self.Bind(wx.EVT_MENU, lambda evt, p=i: self.OnSelectProtocol(p), item)
        menubar.Append(protocolMenu, '&Protocol')

        # Settings Menu
        settingsMenu = wx.Menu()
        resetItem = settingsMenu.Append(wx.ID_ANY, 'Reset Instance', 'Reset ggwave instance')
        self.Bind(wx.EVT_MENU, self.OnReset, resetItem)
        menubar.Append(settingsMenu, '&Settings')

        self.SetMenuBar(menubar)
        self.Show()

    def OnSelectProtocol(self, protocol):
        self.gw.protocol = protocol
        self.Log(f"Protocol set to {protocol}")

    def OnReset(self, event):
        self.gw.switchinstance(-1)
        self.Log("Instance reset")

    def OnTimer(self, event):
        res = self.output_handler.receiver.check_timeout()
        if res == "SENT_NACK":
            self.Log(f"Still waiting for chunks of {self.output_handler.receiver.filename}. Sent NACK.")

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

    def Log(self, msg):
        self.history.AppendText(msg + "\n")

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

    def set_gw(self, gw_instance):
        self.gw = gw_instance
        self.receiver = FileReceiver(self.gw)

    def data_callback(self, data):
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
