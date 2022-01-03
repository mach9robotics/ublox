#!/usr/bin/env python3

"""
A NTRIP client, streams rtcm msg to ROS message

Adapted from source:
https://github.com/ros-agriculture/ntrip_ros/blob/master/scripts/ntripclient.py
"""

import rospy
import time
from datetime import datetime

#from nmea_msgs.msg import Sentence
from rtcm_msgs.msg import Message

from base64 import b64encode
from threading import Thread

from http.client import HTTPConnection
from http.client import IncompleteRead

# This is to fix the IncompleteRead error
# http://bobrochel.blogspot.com/2010/11/bad-servers-chunked-encoding-and.html
import http.client
def patch_http_response_read(func):
    def inner(*args):
        try:
            return func(*args)
        except http.client.IncompleteRead as e:
            return e.partial
    return inner
http.client.HTTPResponse.read = patch_http_response_read(
    http.client.HTTPResponse.read)

class ntripconnect(Thread):
    def __init__(self, ntc):
        super(ntripconnect, self).__init__()
        self.ntc = ntc
        self.stop = False

    def run(self):
        auth = self.ntc.ntrip_user + ':' + self.ntc.ntrip_pass
        headers = {
            'Ntrip-Version': 'Ntrip/2.0',
            'User-Agent': 'NTRIP ntrip_ros',
            'Connection': 'close',
            'Authorization': 'Basic ' + b64encode(auth.encode("ascii")).hex()
        }
        rospy.loginfo(headers)
        connection = HTTPConnection(self.ntc.ntrip_server)
        connection.request(
            'GET',
            '/'+self.ntc.ntrip_stream,
            self.ntc.nmea_gga,
            headers)
        response = connection.getresponse()
        if response.status != 200: raise Exception("blah")
        buf = bytearray()
        rmsg = Message()
        restart_count = 0

        while not self.stop:
            data = response.read(1)
            if len(data) != 0:
                if data[0] == 211:
                    buf += data
                    data = response.read(2)
                    buf += data
                    cnt = data[0] * 256 + data[1]
                    data = response.read(2)
                    buf += data
                    typ = (data[0] * 256 + data[1]) / 16
                    rospy.loginfo_once("NTRIP connection established at " + \
                        str(datetime.now()))
                    cnt = cnt + 1
                    for x in range(cnt):
                        data = response.read(1)
                        buf += data
                    rmsg.message = buf
                    rmsg.header.seq += 1
                    rmsg.header.stamp = rospy.get_rostime()
                    self.ntc.pub.publish(rmsg)
                    buf = bytearray()
            else:
                ''' If zero length data, close connection and reopen it '''
                time.sleep(5)
                restart_count = restart_count + 1
                rospy.logwarn("Zero length ", restart_count)
                connection.close()
                connection = HTTPConnection(self.ntc.ntrip_server)
                connection.request(
                    'GET',
                    '/'+self.ntc.ntrip_stream,
                    self.ntc.nmea_gga,
                    headers)
                response = connection.getresponse()
                if response.status != 200: raise Exception("blah")
                buf = bytearray()

        connection.close()

class ntripclient:
    def __init__(self):
        rospy.init_node('ntripclient', anonymous=True)

        self.rtcm_topic = rospy.get_param('~rtcm_topic', 'rtcm')
        self.nmea_topic = rospy.get_param('~nmea_topic', 'nmea')

        self.ntrip_server = rospy.get_param('~ntrip_server')
        self.ntrip_user = rospy.get_param('~ntrip_user')
        self.ntrip_pass = rospy.get_param('~ntrip_pass')
        self.ntrip_stream = rospy.get_param('~ntrip_stream')
        self.nmea_gga = rospy.get_param('~nmea_gga')

        self.pub = rospy.Publisher(self.rtcm_topic, Message, queue_size=10)

        self.connection = None
        self.connection = ntripconnect(self)
        self.connection.start()

    def run(self):
        rospy.spin()
        if self.connection is not None:
            self.connection.stop = True

if __name__ == '__main__':
    c = ntripclient()
    c.run()
