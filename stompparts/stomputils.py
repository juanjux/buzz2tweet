import sys, socket, time, logging
import stomp
from pprint import pprint

 
class StompMessenger(object):
    def __init__(self, host = 'localhost', port = 61613 ):
        # XXX Better logging, to a file...
        logging.basicConfig()
        self.connected = False
        
        while not self.connected:
            try:
               # connect to the stompserver
               self.conn = stomp.Connection(host_and_ports=[(host, port)])
               self.conn.start()
               self.conn.connect()
               self.connected = True
            except socket.error:
                print 'Warning: socket error connecting to stomp server at %s:%s' % (host, str(port))
                
    def __del__(self):
        self.conn.disconnect()
        
    def sendmessage(self, queue, message):
        self.conn.send(message, destination=queue)
