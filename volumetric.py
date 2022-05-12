"""
basic volumetric functionality with plane alignment
"""

import argparse
import logging
import time
import sys

import threading as tr
import numpy as np

from thePeckingOrder import planeAlignment, zmqComm


class Karen:
    """
    she manages all the things
    """
    def __init__(self, walky_talky, nplanes, alignThreshold):
        """

        walkyTalky: should be a walkytalky class object that communicates with the labview scope controls
        """
        self.wt = walky_talky
        self.nPlanes = nplanes
        self.alignTimeThresh = alignThreshold

        self.running = True
        self.targetAcquired = False
        self.volumeScanning = False
        self.targetImage = None
        self.aligning = False
        self.alignmentParams = {'step': 3, 'reps': 5}
        self.lastAlignedTime = time.time()
        self.alignmentMoveDictionary = {0: -self.alignmentParams['step']*2,
                                        1: -self.alignmentParams['step'],
                                        2: 0,
                                        3: self.alignmentParams['step'],
                                        4: self.alignmentParams['step']*2}

        # stop whatever is happening and start scanning target plane
        self.resetToTarget()
        # start acquisition of target plane
        self.acquireTargetThread = tr.Thread(target=self.acquireTarget)
        self.acquireTargetThread.start()

        self.mainLoopThread = tr.Thread(target=self.mainLoop)
        self.mainLoopThread.start()

    def resetToTarget(self):
        # stop the acquisition & move to target
        self.wt.pub.socket.send(b"RESET")
        time.sleep(1)
        self.wt.pub.socket.send(b"s4 p2")
        self.wt.pub.socket.send(b"RUN")
        time.sleep(1)
        self.wt.pub.socket.send(b"RESET")
        time.sleep(1)
        # start continuous acquisition
        self.wt.pub.socket.send(b"s1 s3")
        self.wt.pub.socket.send(b"RUN")
        time.sleep(1)
        self.wt.pub.socket.send(b"RESET")

    def acquireTarget(self):
        self.wt.make_current()
        logging.info('acquiring target plane')
        while len(self.wt.images) <= 15:
            pass
        self.targetAcquired = True
        self.targetImage = np.median(self.wt.images)
        logging.info('target plane acquired')
        return

    def startVolumeScanning(self):
        self.wt.pub.socket.send(f's4 s2 p0 "1000 (p1 "20 (s3 s5? p3 "20){self.nPlanes})5000'.encode()) # n planes and arb high number for reps
        self.wt.pub.socket.send(b"RUN")
        self.volumeScanning = True

    def runAlignment(self):
        self.aligning = True
        self.volumeScanning = False
        logging.info('beginning alignment...')
        self.resetToTarget()
        compStack = self.wt.gather_stack(spacing=self.alignmentParams['step'], reps=self.alignmentParams['reps'])
        pa = planeAlignment.PlaneAlignment(target=self.targetImage, stack=compStack, method='otsu')
        myMatch = pa.match_calculator()
        moveAmount = self.alignmentMoveDictionary[myMatch]
        if moveAmount != 0:
            self.wt.move_piezo_n(moveAmount)
        logging.info(f'alignment: status: completed with {moveAmount} movement')
        self.last_aligned_time = time.time()
        self.aligning = False

    def mainLoop(self):
        while self.running:
            if not self.targetAcquired:
                pass
            elif time.time() - self.lastAlignedTime >= self.alignTimeThresh:
                self.runAlignment()
            else:
                if not self.volumeScanning and not self.aligning:
                    self.startVolumeScanning()
                    time.sleep(1)
            if KeyboardInterrupt:
                print("Boss Slain")
                self.running = False
                sys.exit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--nplanes', type=float, required=True)
    parser.add_argument('--align_t', type=int, default=450)

    args = parser.parse_args()

    myWalky = zmqComm.WalkyTalky(outputPort='5005', inputIP='tcp://10.122.170.21:', inputPort=4701)
    Karen(walky_talky=myWalky, nplanes=args.nplanes, alignThreshold=args.align_t)
