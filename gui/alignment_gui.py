from thePeckingOrder import zmqComm, planeAlignment

from PyQt5 import QtWidgets, uic, QtCore
from PyQt5.Qt import QApplication

from datetime import datetime as dt

import qdarkstyle

import threading as tr
import pyqtgraph as pg
import numpy as np

import os
import logging
import time
import zmq

logging.basicConfig(level=logging.INFO)


exit_event = tr.Event()


class PlaneAligner(QtWidgets.QMainWindow):
    def __init__(self, walkytalky, stimBuddyPorts):
        super(PlaneAligner, self).__init__()
        self.running = True
        self.locPath = os.path.dirname(os.path.realpath(__file__))
        self.UIpath = os.path.join(self.locPath, 'alignment_gui.ui')
        uic.loadUi(self.UIpath, self)

        self.wt = walkytalky
        self.alignmentStatus = False
        self.runningSequences = False

        # self.main_widget = QtWidgets.QWidget(self)
        # self.main_layout = QtWidgets.QVBoxLayout(self.main_widget)

        try:
            self.displayImg = self.wt.images[-1]
        except IndexError:
            self.displayImg = np.zeros([512,512])

        self.lastAlignedTime = time.time()

        self.viewImages = pg.ImageView(parent=self.targetContainer)
        self.viewImages.setImage(self.displayImg, autoRange=False)

        self.viewLive = pg.ImageView(parent=self.currentPlane)
        self.viewLive.setImage(self.displayImg)

        # self.viewLive.setParent(self.currentPlane)

        self.quitbutton.clicked.connect(self.closeEvent)
        self.newTargetButton.clicked.connect(self.update_image)
        self.runAlignmentButton.clicked.connect(self.run_alignment)
        self.runSequenceAlignmentButton.clicked.connect(self.run_alignment_sequence)
        self.stimulusCheck.clicked.connect(self.safetyEnabled)

        self.n = 0
        self.img_lens = 0
        self.losses = []
        self.planes_n = []

        self.graphWidget = pg.PlotWidget(parent=self.lossGraph, autoscale=True, history=1500)
        self.graphWidget.setGeometry(0, 0, self.lossGraph.width(), self.lossGraph.height())

        self.graphTimer = QtCore.QTimer()
        self.graphTimer.setInterval(1000)
        self.graphTimer.timeout.connect(self.graphfxn)
        self.graphTimer.start()

        self.imgUpdater = QtCore.QTimer()
        self.imgUpdater.setInterval(500)
        self.imgUpdater.timeout.connect(self.update_live)
        self.imgUpdater.start()

        self.flushTimer = QtCore.QTimer()
        self.flushTimer.setInterval(600000)
        self.flushTimer.timeout.connect(self.flush)
        self.flushTimer.start()

        framelist = [self.plane0, self.plane1, self.plane2, self.plane3, self.plane4]
        self.planeImgs = [pg.ImageView(parent=frame) for frame in framelist]

        self.aligntarget = pg.ImageView(parent=self.alignTargetFrame)
        self.alignchoice = pg.ImageView(parent=self.alignChosenFrame)

        self.planeLabels = [self.plane0_val, self.plane1_val, self.plane2_val, self.plane3_val, self.plane4_val]
        [pval.setText(str(0)) for pval in self.planeLabels]

        self.pstimPub = zmqComm.Publisher(stimBuddyPorts['wt_output'])
        self.pstimSub = zmqComm.Subscriber(stimBuddyPorts['wt_input'])

        self.pstim_msg_thread = tr.Thread(target=self.pstim_msg_reception)
        self.pstim_msg_thread.start()

    def update_live(self):
        try:
            self.viewLive.setImage(self.wt.images[-1], autoRange=False)
        except IndexError:
            pass

    def flush(self):
        self.wt.make_current()

    def graphfxn(self):
        curr_l = len(self.wt.images)
        if curr_l != self.img_lens and np.sum(self.displayImg) != 0:
            self.img_lens = curr_l
            self.n += 1
            pa = planeAlignment.PlaneAlignment(self.wt.images[-1], self.displayImg, method='otsu')
            loss = pa.lossReturn()
            self.losses.append(loss)
            self.planes_n.append(self.n)
            self.graphWidget.plot(self.planes_n, self.losses)
            # self.graphWidget.setYRange(0, 1, padding=0)

    def update_image(self):
        n_frames = self.n_imgs.value()
        self.displayImg = np.median(self.wt.images[-n_frames:], axis=0)
        self.viewImages.setImage(self.displayImg, autoRange=False)
        self.output(f'target updated using{n_frames}', True)

    def closeEvent(self, event):
        self.imgUpdater.stop()
        self.graphTimer.stop()
        self.flushTimer.stop()
        self.running = False
        self.runningSequences = False
        try:
            self.wt.kill()
        except:
            pass
        try:
            self.wt.join()
        except:
            pass
        try:
            self.pstim_msg_thread.join()
        except:
            pass

        try:
            exit_event.set()
        except:
            pass
        try:
            self.pstim_msg_thread.kill()
        except:
            pass

        self.close()
        sys.exit()

    def pstim_msg_reception(self):
        # this will trigger alignment running from msgs in pstim
        while self.running:
            topic = self.pstimSub.socket.recv_string()
            msg = self.pstimSub.socket.recv_pyobj()
            match topic:
                case 'stimbuddy':
                    match msg:
                        case 'proceed':
                            self.output('received pause confirmation from pstim', True)
                            self.run_alignment(safe=True)
                        case _:
                            print(f'{msg}: message not understood')
                case _:
                    print(f'{topic}: topic not understood')

    def run_alignment_sequence(self):
        safetyMode = self.stimulusCheck.isChecked()
        checkStatus = self.runSequenceAlignmentButton.isChecked()

        if checkStatus:
            self.output('triggered alignment sequence', True)
            self.total_timer_ms = int(self.n_mins.value() * 60 * 1000)

            if safetyMode:
                self.run_safe_alignment_timer()
            else:
                self.run_raw_alignment_timer()
        else:
            self.output('sequencing disabled', True)
            self.kill_timers()

    def run_safe_alignment_timer(self):
        self.alignmentSequencer_safe = QtCore.QTimer(singleShot=True)
        self.alignmentSequencer_safe.setInterval(self.total_timer_ms) # *1000 for ms
        self.alignmentSequencer_safe.timeout.connect(self.askPstimForPermission)
        self.alignmentSequencer_safe.start()

    def run_raw_alignment_timer(self):
        self.alignmentSequencer_raw = QtCore.QTimer(singleShot=True)
        self.alignmentSequencer_raw.setInterval(self.total_timer_ms) # *1000 for ms
        self.alignmentSequencer_raw.timeout.connect(self.run_alignment)
        self.alignmentSequencer_raw.start()

    def kill_timers(self):
        try:
            self.alignmentSequencer_raw.stop()
        except:
            pass
        try:
            self.alignmentSequencer_safe.stop()
        except:
            pass

    def askPstimForPermission(self):
        self.output('asked pstim to pause', True)
        # asks pstim to pause
        self.pstimPub.socket.send_string('alignment', zmq.SNDMORE)
        self.pstimPub.socket.send_pyobj("pause")
    def thankPstim(self):
        self.output('asked pstim to unpause', True)
        # resumes pstim
        self.pstimPub.socket.send_string('alignment', zmq.SNDMORE)
        self.pstimPub.socket.send_pyobj("unpause")

    def run_alignment(self, safe=False):
        self.output(f'alignment: status: initiated')

        stepSize = self.n_um.value()
        someMovementDictionary = {
            0: -stepSize*2,
            1: -stepSize,
            2: 0,
            3: stepSize,
            4: stepSize*2
        }

        self.wt.pub.socket.send(b"RESET")
        time.sleep(1)
        self.compStack = self.wt.gather_stack(spacing=stepSize, reps=self.n_reps.value())
        pa = planeAlignment.PlaneAlignment(target=self.displayImg, stack=self.compStack, method='otsu')
        self.myMatch = pa.match_calculator()
        moveAmount = someMovementDictionary[self.myMatch]
        if moveAmount != 0:
            self.wt.move_piezo_n(moveAmount)
        self.output(f'alignment: status: completed with {moveAmount} movement')

        textOut = self.scanningParams.toPlainText()
        self.wt.pub.socket.send(textOut.encode())
        self.wt.pub.socket.send(b"RUN")
        if safe:
            self.thankPstim()

        self.run_alignment_sequence()

        self.matchVals = pa.match_val_returns()
        self.update_alignment_tab()

    def update_alignment_tab(self):
        [imgFrame.setImage(self.compStack[n], autoRange=False) for n, imgFrame in enumerate(self.planeImgs)]
        [pval.setText(str(self.matchVals[n])) for n, pval in enumerate(self.planeLabels)]
        self.aligntarget.setImage(self.displayImg)
        self.alignchoice.setImage(self.compStack[self.myMatch])

    def output(self, msg, verbose=False):
        if not verbose:
            self.outputLog.append(f'{dt.now()} {msg}')
        else:
            if self.verboseMode.isChecked():
                self.outputLog.append(f'{dt.now()} {msg}')

    def safetyEnabled(self):
        self.output(f'pstim safety {self.stimulusCheck.isChecked()}', True)



def run():
    app = QApplication([])
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    myWalky = zmqComm.WalkyTalky(outputPort='5005', inputIP='tcp://10.122.170.21:', inputPort=4701)

    alignment_ports = {"wt_output" : '5015', "wt_input": '5016'}

    wind = PlaneAligner(walkytalky=myWalky, stimBuddyPorts=alignment_ports)
    wind.show()
    app.exec()


if __name__ == '__main__':
    run()
