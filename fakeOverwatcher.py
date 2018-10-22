#!/usr/bin/python3
"""
REVISION
--------
This should match what is tested.
"""
overwatcher_revision = 20181012

import socket
import random
import time
import datetime
import queue
import threading
import argparse
import yaml
import os
from overwatcher import Overwatcher


class FakeOverwatcher(Overwatcher):
    def __init__(self, log, server='localhost', port=5000, runAsTelnetTest=False, endr=False):
        #Remmember the test file
        self.file_log = log

        #Use overwatcher init - this blocks in getResult!!!
        super().__init__(log, server, port, runAsTelnetTest, endr)

    def setup_test(self, test):
        """
        No need to parse any YAML file. Can se any option overrides here, as it is called after the defaults.
        """
        #Prepare the revision checking
        self.info['overwatcher revision required'] = overwatcher_revision

        self.name = os.path.splitext(os.path.basename(test))[0] #Used for log file, get only the name
        return

    def config_device(self):
        """
        No device configuration needed.
        """
        return

    def sock_create(self):
        """
        We are a server, not a client
        """
        self.log("Creating socket")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((self.server, self.port))

        self.log("Waiting for clients")
        s.listen()
        return s

    def sock_close(self, s):
        """
        Server, again.
        """
        if s is not None:
            s.close()

        return




if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="This is the fake version!")

    parser.add_argument('log', help='Log file to use')
    parser.add_argument('--server', help='IP to bind to',
            default='localhost')
    parser.add_argument('--port', help='Port to bind to',
            type=int, default=3000)
    parser.add_argument('--endr', help='Send a \r\n instead of just \n',
            action='store_true')

    args = parser.parse_args()


    test = FakeOverwatcher(args.log, server=args.server, port=args.port, endr=args.endr)
