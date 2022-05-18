import logging

import numpy as np

from thePeckingOrder.filters import threshold_otsu

logging.basicConfig(level=logging.DEBUG)  # NOTSET, DEBUG, INFO, WARNING


class PlaneAlignment:
    def __init__(self, target, stack, method):
        approved_methods = {'mean': np.mean,
                            'otsu': threshold_otsu}

        assert(method in approved_methods.keys()), f'method must be approved method: {approved_methods.keys()}'
        self.binarize_method = approved_methods[method]

        self.target_image = target
        self.image_stack = stack

    def match_calculator(self):
        binary_imgs = [image > self.binarize_method(image) for image in self.image_stack]
        target_image = self.target_image > self.binarize_method(self.target_image)

        self.match_vals = []
        for n, q in enumerate(binary_imgs):
            accuracy = self.calculate_similarity(target_image, q)
            logging.debug(f'image {n} is {accuracy} accurate')
            self.match_vals.append(accuracy)
        return np.where(self.match_vals == np.max(self.match_vals))[0][0]

    def lossReturn(self):
        binary_img = self.image_stack >= self.binarize_method(self.image_stack)
        target_image = self.target_image >= self.binarize_method(self.target_image)
        return self.calculate_similarity(target_image, binary_img)


    @staticmethod
    def calculate_similarity(pred, true, k=1):
        # only works on binarized inputs
        intersection = np.sum(pred[true==k]) * 2.0
        dice = intersection / (np.sum(pred) + np.sum(true))
        return dice

"""
class decrepitPlaneAlignment:
    def __init__(self, port='5000', ip='127.0.0.1', method='otsu', image_receiver='python', setSize=9,):
        '''

        :param port: image source
        :param ip: image source
        :param method: method works only on binarized images: this is the binarization method
        :param image_receiver: whether the images are coming from the labview style
        :param setSize: this is a jank way to know when your done getting images -- should move to a msg system

        '''

        assert(isinstance(port, str)), 'port must be string'
        assert(isinstance(ip, str)), 'ip must be string'

        approved_methods = {'mean': np.mean,
                            'otsu': threshold_otsu}

        assert(method in approved_methods.keys()), f'method must be approved method: {approved_methods.keys()}'

        image_receiver = image_receiver.lower()  # in case someone wants to LabVIEW
        image_receivers = {'python': self.img_receiver_local,
                            'labview': self.img_receiver_external}
        assert(image_receiver in image_receivers.keys()), f'image receiver must be one of {image_receivers.keys()}'

        if image_receiver == "labview":
            # for some reason they like the json package
            import json

        self.binarize_method = approved_methods[method]
        self.img_receiver = image_receivers[image_receiver]

        self.context, self.socket = self.init_comms(port, ip)

        self.images = []
        self.curr_l = -1
        self.targetImage = None

        self.setSize = setSize

        # likely not strictly necessary as we wait for the stack, but cleaner isolated
        self.img_reception_thread = tr.Thread(target=self.image_receiving)
        self.img_reception_thread.start()

    def image_receiving(self):
        while self.curr_l < self.setSize:
            logging.debug(f'receiving imgs, currently have {len(self.images)}')
            img, topic = self.img_receiver(self.socket)
            if topic == 'target':
                logging.info('received target')
                self.targetImage = img
            else:
                self.images.append(img)
                self.curr_l = len(self.images)

        # likely need to extricate this bit later and leave image_receiving separate
        # this is convenient because it ensure we finished receiving all the images
        # strictly speaking we can always calculate matches -- regardless of the number present
        self.top_match = self.match_returner()
        logging.info(f'calculated top match {self.top_match}')

    # this should asynchronously be done "on-change" of the image_list attr
    def match_returner(self):
        assert(self.targetImage is not None), 'No target image found'
        binary_imgs = []
        for image in self.images:
            binary_imgs.append(image > self.binarize_method(image))

        target_image = self.targetImage > self.binarize_method(self.targetImage)
        accs = []
        for n,q in enumerate(binary_imgs):
            accuracy = self.calculate_similarity(target_image, q)
            logging.debug(f'image {n} is {accuracy} accurate')
            accs.append(accuracy)
        return np.where(accs == np.max(accs))[0][0]

    @staticmethod
    def calculate_similarity(pred, true, k=1):
        # only works on binarized inputs
        intersection = np.sum(pred[true==k]) * 2.0
        dice = intersection / (np.sum(pred) + np.sum(true))
        return dice

    @staticmethod
    def init_comms(port, ip):
        c = zmq.Context()
        socket = c.socket(zmq.SUB)
        socket.connect(ip + port)
        socket.setsockopt(zmq.SUBSCRIBE, b'')
        return c, socket

    # labview image receiver ?
    @staticmethod
    def img_receiver_external(socket):
        msg = socket.recv()
        msg_parts = [part.strip() for part in msg.split(b': ', 1)]
        tag = msg_parts[0].split(b' ')[0]
        # sendtime =  msg_parts[0].split(b' ')[2].decode()
        array = np.array(json.loads(msg_parts[1]))[:, 32:]  # assuming the following message structure: 'tag: message'
        return array, tag

    # python image sender
    @staticmethod
    def msg_sender_local(socket, data, string):
        my_msg = dict(dtype=str(data.dtype), shape=data.shape)
        socket.send_string(string, zmq.SNDMORE)
        socket.send_json(my_msg, zmq.SNDMORE)
        socket.send(data)

    # python image receiver
    @staticmethod
    def img_receiver_local(socket, ):
        msg_topic = socket.recv_string()
        msg_dict = socket.recv_json()
        msg = socket.recv()
        _img = np.frombuffer(bytes(memoryview(msg)), dtype=msg_dict['dtype'])
        img = _img.reshape(msg_dict['shape'])
        return np.array(img), msg_topic


if __name__ == '__main__':
    # used_ip_address = '127.0.0.1'
    used_ip_address = 'tcp://localhost:'
    used_port = '4701'

    plane_aligner = PlaneAlignment(port=used_port, ip=used_ip_address, method='mean', setSize=5)
"""
