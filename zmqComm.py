import zmq
import logging

import threading as tr

from datetime import datetime as dt

logging.basicConfig(level=logging.DEBUG)  # NOTSET, DEBUG, INFO, WARNING


class WalkyTalky:
    def __init__(self, outputPort, inputIP, inputPort, savePath=None, subTopic=""):
        """
        generic back & forth communication with LabVIEW

        :param ip:
        :param outputPort: port to send messages to labivew
        :param inputPort: port to input images from labview
        :param savePath:
        """
        self.sub = Subscriber(port=inputPort, topic=subTopic, ip=inputIP)
        self.pub = Publisher(port=outputPort)
        self.savePath = savePath

        self.running = True

        self.messages = []
        self.timestamps = []
        self.msg_receiving_thread = tr.Thread(target=self.msg_receiver)

    def msg_receiver(self):
        while self.running:
            data = self.sub.socket.recv()
            self.save(data)
            self.messages.append(data)
            self.timestamps.append(dt.now())
            logging.debug(f'{dt.now()} received {data}')

    def save(self, data):
        if self.savePath is not None:
            if "saveStream" not in vars(self):
                self.saveStream = self.init_saving(self.savePath)
            self.saveStream.write(f"{dt.now()}_{data}")
            self.saveStream.write("\n")
            self.saveStream.flush()

    @staticmethod
    def init_saving(file_path):
        import os
        val_offset = 0
        newpath = file_path
        while os.path.exists(newpath):
            val_offset += 1
            newpath = file_path[:file_path.rfind('/') + 1] + file_path[
                                                             file_path.rfind('/') + 1:][:-4] \
                      + '_' + str(val_offset) + '.txt'

        logging.info(f"{dt.now()} Saving data to {file_path}")
        filestream = open(file_path, "a")
        filestream.write(f"{dt.now()} \n")
        return filestream


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
