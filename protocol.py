from planeAlignment import PlaneAlignment as pa
from zmqComm import WalkyTalky as wt

import time
import json

import numpy as np
import threading as tr


class Protocol:
    def __init__(self, port_info, stack_size=7, n_reps=3, z_size=2.0):
        self.running = True
        self.comms = wt(port_info['outputPort'], port_info['inputIP'], port_info['inputPort'], port_info['savePath'], subTopic=b'frame')
        self.aligner = pa(None, None, method='otsu')

        self.n_reps = n_reps
        self.stack_size = stack_size
        self.z_size = z_size

        self.comms.pub.socket.send(b' ')

    def run_image_gathering(self):

        ## at the moment this assumes wt only receives messages that includes images
        ## attempting to leverage the image finite samples feature to grab each relative chunk of data
        ## gets n reps, waits til its received, repeats across stacksize
        ## if more convienient for labview we can protocolize the whole thing and send in one go
        ## important piece is getting the images in a list of order [Target0..TargetN, img1_0...img1_N,...imgN_N]


        ## f's2 p0 "100 (p1 "20(s3 s5? p3 "20){self.stack_size}){self.n_reps}'
        ## outMsg = f'setProtocol: s2 p0 "100(p1 "20(s3 s5? p3 "20){self.stack_size}){self.n_reps}'.encode()

        outMsg = f'setProtocol: s2 p0 "100(p1 "20(s3 s5? p3 "20){self.stack_size}){self.n_reps}'.encode()
        someRunMsg = b'RUN'

        # send someRunMsg
        startCaring = True # start paying attention to the images going out from scope
        # self.comms.messages = [] # reflush the list of messages

        self.comms.pub.socket.send_string(f'scanner: run_finite{self.n_reps} zmq: target')

        # wait and get the full stack
        while not len(self.comms.messages) >= self.n_reps:
            pass

        self.comms.pub.socket.send_string(f'piezo: move_rel{-self.z_size*(self.stack_size//self.n_reps)}')

        for n in range(self.stack_size):
            self.comms.pub.socket.send_string(f'scanner: run_finite{self.n_reps} zmq: frame_{n}')

            while not len(self.comms.messages) >= (self.n_reps * (n + 2)):
                pass

            self.comms.pub.socket.send_string(f'piezo: move_rel+{self.z_size}')

    def run_alignment(self):
        self.run_image_gathering()
        split_lists = list(self.divide_chunks(self.comms.messages, self.n_reps))

        self.aligner.target_image = np.median(split_lists[0], axis=0)
        self.aligner.image_stack = [np.median(split_lists[n], axis=0) for n in range(len(split_lists[1:]))]
        self.aligner.match_calculator()

        top_match = np.where(self.aligner.match_vals == np.max(self.aligner.match_vals))[0][0]

        # img stack val between 0 - stack size
        move_correction = (top_match - (self.stack_size//self.n_reps)) * self.z_size
        if move_correction >= 0:
            move_correction = '+' + str(move_correction)
        else:
            move_correction = '-' + str(move_correction)

        self.comms.pub.socket.send_string(f'piezo: move_rel{move_correction}')

    def kill(self):
        self.running = False

    # labview image receiver ?
    @staticmethod
    def img_receiver_external(socket):
        msg = socket.recv()
        msg_parts = [part.strip() for part in msg.split(b': ', 1)]
        tag = msg_parts[0].split(b' ')[0]
        # sendtime =  msg_parts[0].split(b' ')[2].decode()
        array = np.array(json.loads(msg_parts[1]))[:, 32:]  # assuming the following message structure: 'tag: message'
        return array, tag

    @staticmethod
    def divide_chunks(l, n):
        # looping till length l
        for i in range(0, len(l), n):
            yield l[i:i + n]


# both frame and time protocol will likely have to become part of stimulusBuddy

class FrameProtocol(Protocol):
    def __init__(self, frame_threshold=1000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # update every n frames of imaging
        self.frame_threshold = frame_threshold

        # check len(self.comms.messages)
    def sequencer(self):
        while self.running:
            if len(self.comms.messages) >= self.frame_threshold:
                self.run_alignment()
                self.comms.messages = []


class TimeProtocol(Protocol):
    def __init__(self, t_threshold=600, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.t_threshold = t_threshold
        self.time_0 = time.time()

        self.sequence_thread = tr.Thread(target=self.sequencer)
        self.sequence_thread.start()

    def sequencer(self):
        while self.running:
            curr_t = time.time()

            if curr_t - self.time_0 >= self.t_threshold:
                self.run_alignment()
                self.time_0 = curr_t

    def kill(self):
        super().kill()
        self.sequence_thread.join()


if __name__ == '__main__':
    walky_info = {"outputPort" : 5555,
                "inputPort" : 5556,
                "inputIP" : '127.0.0.1',
                  "savePath" : None}
    Protocol(walky_info)
