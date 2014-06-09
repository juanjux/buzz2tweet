#!/usr/bin/env python

import time
import sys
import stomp

conn = stomp.Connection()
conn.start()
conn.connect()
conn.send(' '.join(sys.argv[2:]), destination=sys.argv[1])
conn.disconnect()

