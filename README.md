# thePeckingOrder
python-based interfacing with labview framework of image acquisition 

<br /><br />  

Example to run the GUI to drive alignment
```
from PyQt5.Qt import QApplication

from thePeckingOrder import zmqComm
from thePeckingOrder.gui import alignment_gui

import qdarkstyle

def alignment_gui():
    app = QApplication([])
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    # handles communication with labview
    myWalky = zmqComm.WalkyTalky(outputPort='5005', inputIP='tcp://10.122.170.21:', inputPort='4701')
    pa = alignment_gui.PlaneAligner(walkytalky=myWalky)
    pa.show()
    app.exec()
```

We create a WalkyTalky object that communicates bidirectionally with LabVIEW  
We add the walkytalky into our gui and run it