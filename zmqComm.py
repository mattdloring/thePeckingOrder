import zmq
import logging
import json
import time
import sys

import threading as tr
import numpy as np

from datetime import datetime as dt

from thePeckingOrder.filters import threshold_otsu

logging.basicConfig(level=logging.DEBUG)  # NOTSET, DEBUG, INFO, WARNING


class WalkyTalky:
    def __init__(self, outputPort, inputIP, inputPort):
        self.sub = Subscriber(port=inputPort, ip=inputIP)
        self.pub = Publisher(port=outputPort)

        self.running = True

        self.images = []
        self.timestamps = []

        self.msg_receiving_thread = tr.Thread(target=self.msg_receiver)
        self.msg_receiving_thread.start()

    def kill(self):
        self.running = False
        sys.exit()

    def msg_receiver(self):
        while self.running:
            data = self.sub.socket.recv()
            msg_parts = [part.strip() for part in data.split(b': ', 1)]
            # tag = msg_parts[0].split(b' ')[0]
            dateString = str(msg_parts[0]).split(' ')[2]
            timestamp = dt.strptime(dateString, "%H:%M:%S.%f").time()
            array = np.array(json.loads(msg_parts[1]))[:,
                    32:]  # assuming the following message structure: 'tag: message'

            # logging.info(f'{dt.now()} received data')

            self.images.append(array)
            self.timestamps.append(timestamp)

    def make_current(self):
        relTimer = dt.now().time()
        self.clip_from_t(relTimer)

    def clip_from_t(self, t):

        if self.timestamps[-1] < t:
            self.timestamps = []
            self.images = []
            return

        for n, time in enumerate(self.timestamps):
            if time < t:
                pass
            else:
                break
        self.timestamps = self.timestamps[n:]
        self.images = self.images[n:]

    def move_piezo_n(self, n):
        # move n down
        if n > 0:
            self.pub.socket.send(f'(pplus){n * 2}'.encode())
        else:
            self.pub.socket.send(f'(pminus){abs(n) * 2}'.encode())

        time.sleep(0.2)
        self.pub.socket.send(b"RUN")
        time.sleep(1)
        self.pub.socket.send(b"RESET")

    def gather_stack(self, spacing, reps):
        # hard coded atm for a 5-stack, 5um steps. reps flexible
        # stop scanning
        self.pub.socket.send(b"s4")
        self.pub.socket.send(b"RUN")

        time.sleep(1)
        self.pub.socket.send(b"RESET")
        time.sleep(1)

        # clear stack
        try:
            self.make_current()
        except IndexError:
            pass # here if already empty

        # get target plane
        self.pub.socket.send(f'p0 s2 "500 (s3 s5? "20){reps} p1'.encode())
        self.pub.socket.send(b"RUN")

        while len(self.timestamps) <= reps - 1:
            pass

        target = np.median(self.images, axis=0)
        self.make_current()

        stackAbove = []

        # GET ONE ABOVE
        self.pub.socket.send(b"RESET")
        time.sleep(1)
        self.move_piezo_n(spacing)
        time.sleep(1)
        self.pub.socket.send(f'(s3 s5? "20){reps}'.encode())
        self.pub.socket.send(b"RUN")
        while len(self.timestamps) <= reps - 1:
            pass
        someImage = np.median(self.images, axis=0)
        stackAbove.append(someImage)
        self.make_current()

        # GET SECOND ABOVE
        self.pub.socket.send(b"RESET")
        time.sleep(1)
        self.move_piezo_n(spacing)
        time.sleep(1)
        self.pub.socket.send(f'(s3 s5? "20){reps}'.encode())
        self.pub.socket.send(b"RUN")
        while len(self.timestamps) <= reps - 1:
            pass
        someImage = np.median(self.images, axis=0)
        stackAbove.append(someImage)
        self.make_current()

        # GET FIRST BELOW
        stackBelow = []
        self.pub.socket.send(b"RESET")

        time.sleep(1)
        self.move_piezo_n(-spacing*3)
        time.sleep(1)

        self.pub.socket.send(f'(s3 s5? "20){reps}'.encode())
        self.pub.socket.send(b"RUN")
        while len(self.timestamps) <= reps - 1:
            pass
        someImage = np.median(self.images, axis=0)
        stackBelow.append(someImage)
        self.make_current()
        # GET SECOND BELOW
        self.pub.socket.send(b"RESET")
        time.sleep(1)
        self.move_piezo_n(-spacing)
        time.sleep(1)
        self.pub.socket.send(f'(s3 s5? "20){reps}'.encode())
        self.pub.socket.send(b"RUN")
        while len(self.timestamps) <= reps - 1:
            pass
        someImage = np.median(self.images, axis=0)
        stackBelow.append(someImage)
        self.make_current()

        time.sleep(1)

        self.pub.socket.send(b"RESET")
        time.sleep(1)

        offsetBack = spacing*2*2
        self.pub.socket.send(f"(pplus){offsetBack} s1 s3".encode())
        self.pub.socket.send(b"RUN")

        time.sleep(1)
        self.pub.socket.send(b"RESET")
        time.sleep(1)

        finalStack = [stackBelow[-1], stackBelow[0], target, stackAbove[0], stackAbove[-1]]
        return finalStack


class Subscriber:
    """
    Subscriber wrapper class for zmq.
    Default topic is every topic ("").
    """
    def __init__(self, port="1234", topic="", ip=None):
        self.port = port
        self.topic = topic
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)

        if ip is None:
            ip = 'tcp://localhost:'
        if not isinstance(ip, str):
            ip = str(ip)

        self.socket.connect(ip + str(self.port))

        self.socket.subscribe(self.topic)
        logging.info(f"{dt.now()} Subscriber initialized on {ip + str(self.port)}")

    def kill(self):
        self.socket.close()
        self.context.term()


class Publisher:
    """
    Publisher wrapper class for zmq.
    """
    def __init__(self, port="1234"):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("tcp://*:" + str(self.port))
        logging.info(f"{dt.now()} Publisher initialized on {'tcp://localhost:' + str(self.port)}")

    def kill(self):
        self.socket.close()
        self.context.term()
