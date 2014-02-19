import struct
import SocketServer
from base64 import b64encode
from hashlib import sha1
from mimetools import Message
from StringIO import StringIO
import _pyvicon
import json
import numpy as np
import _transformations as tf

global viconServer

class WebSocketsHandler(SocketServer.StreamRequestHandler):
    magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

    def setup(self):
        SocketServer.StreamRequestHandler.setup(self)
        print "connection established", self.client_address
        self.handshake_done = False

    def handle(self):
        while True:
            if not self.handshake_done:
                self.handshake()
            else:
                self.read_next_message()

    def read_next_message(self):
        length = ord(self.rfile.read(2)[1]) & 127
        if length == 126:
            length = struct.unpack(">H", self.rfile.read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self.rfile.read(8))[0]
        masks = [ord(byte) for byte in self.rfile.read(4)]
        decoded = ""
        for char in self.rfile.read(length):
            decoded += chr(ord(char) ^ masks[len(decoded) % 4])
        self.on_message(decoded)

    def send_message(self, message):
        self.request.send(chr(129))
        length = len(message)
        if length <= 125:
            self.request.send(chr(length))
        elif length >= 126 and length <= 65535:
            self.request.send(chr(126))
            self.request.send(struct.pack(">H", length))
        else:
            self.request.send(chr(127))
            self.request.send(struct.pack(">Q", length))
        self.request.send(message)

    def handshake(self):
        data = self.request.recv(1024).strip()
        headers = Message(StringIO(data.split('\r\n', 1)[1]))
        if headers.get("Upgrade", None) != "websocket":
            return
        print 'Handshaking...'
        key = headers['Sec-WebSocket-Key']
        digest = b64encode(sha1(key + self.magic).hexdigest().decode('hex'))
        response = 'HTTP/1.1 101 Switching Protocols\r\n'
        response += 'Upgrade: websocket\r\n'
        response += 'Connection: Upgrade\r\n'
        response += 'Sec-WebSocket-Accept: %s\r\n\r\n' % digest
        self.handshake_done = self.request.send(response)

    def on_message(self, message):
        print message
        (t, x, y, z, roll, pitch, yaw) = viconServer.getData()
        (t, x, y, z, roll, pitch, yaw) = [t/100, x/1000, y/1000, z/1000, roll, pitch, yaw]
        R = tf.euler_matrix(roll, pitch, yaw)
        vf = R*np.mat([1,0,0,0]).T
        vu = R*np.mat([0,0,1,0]).T
        msg = json.dumps([x,y,z,float(vf[0]),float(vf[1]),float(vf[2]), \
                         float(vu[0]), float(vu[1]), float(vu[2])])
        print msg
        self.send_message(msg)

if __name__ == "__main__":
    print "Connecting to Vicon server..."
    viconServer = _pyvicon.ViconStreamer()
    viconServer.connect("10.0.0.102", 800)

    model_name = "GPSReceiverHelmet-goodaxes:GPSReceiverHelmet01"
    # Unlabeled0 is top
    # Unlabeled1 is front
    viconServer.selectStreams(["Time"] + ["{} <{}>".format(model_name, s) for s in ("t-X", "t-Y", "t-Z", "a-X", "a-Y", "a-Z")])

    viconServer.startStreams()

    # Wait for first data to come in
    while viconServer.getData() is None: pass
    
    server = SocketServer.TCPServer(
        ("localhost", 9999), WebSocketsHandler)
    server.serve_forever()

    viconServer.stopStreams()
