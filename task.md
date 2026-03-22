# Task
1. Make a feature to set volume in settings, ggwave encode has volume setting. Read volume docs on ggwave page on github.
2. Remove all default remote command templates, like shutdown / play music. Also make the toggle in settings menu allow remote commands to be executed.
3. Make a folder of sample remote templates, and add a cli app to import them into the appdata folder. This way users can easily add remote commands without having to create them from scratch.
4. Fix bug in file sharing protocol.


## File sharing bugs
1. When handshaking, the receiver sends an answer so quickly that the sender doesn't have time to switch to receive mode, causing the handshake to fail. The sender should wait a bit before sending the handshake request, or the receiver should wait a bit before sending the answer. This happens everywhere so often that we call it SAR (Send after receive) issue. It happens after sending the file / before nack, after nack / before nacked chunks, and everywhere where it communicates. Make a 500 ms delay before responding to every request in all places: in file send and remote query protocol.
2. Dont know what's happening, but sometimes after eof is sent and the receiver sends the nack, the sender sends something else at the same time (overlapped signals) and everyone gets confused. Investigate this issue.