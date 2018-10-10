#!/usr/bin/python3

import socket
import random
import time
import datetime
import queue
import threading
import argparse
import yaml
import os


class Overwatcher():
    """

    TEST AUTOMATION BASED ON SERIAL CONSOLE CONTROL AND OUTPUT.

    """

    """
    -------------------------MAIN SETUP FUNCTION. Reads the test file. Can be overloaded
    """
    def setup_test(self, test):
        """
        Function used to setup all test configurations. 

        NOTE: defaults are set before this is called, so only set what you need.
        NOTE: for backwards compatibility, this should be kept
        """
        self.name = os.path.splitext(os.path.basename(test))[0] #Used for log file, get only the name
        self.full_name = os.path.abspath(test) #Also save the full file path in the logs, because you never know

        tf = open(test, "r")
        elems = list(yaml.safe_load_all(tf))[0]

        #Thanks to YAML this was easy
        self.info = dict(elems['info'])
        self.markers = dict(elems['markers'])
        self.prompts = list(elems['prompts'])
        self.triggers = dict(elems['triggers'])
        self.actions = dict(elems['actions'])

        self.config_seq = list(elems['initconfig'])
        self.test_seq = list(elems['test'])

        #What we need to worry about are the options
        for opt in elems['options']:
            setattr(self, opt, elems['options'][opt])
    """
    -------------------------TEST RESULT FUNCTIONS, called on test ending. Can be overloaded.
    """
    def mytest_timeout(self):
        """
        Trying to improve the timeout problem. Sometimes the socket fluctuates and
        overwatcher misses some output. This should be solved with a CR.
        """
        if self.counter["test_timeouts"] == 0:
            self.setResult("timeout")
        else:
            self.counter["test_timeouts"] -= 1
            self.log("GOT A TIMEOUT, giving it another try...we have", self.counter["test_timeouts"], "left")
            self.mainTimer = self.timer_startTimer(self.mainTimer)
            if self.telnetTest is False:
                #On telnet no need to send a CR
                self.sendDeviceCmd("") #Send a CR


    def mytest_failed(self):
        self.setResult("failed")

    def mytest_ok(self):
        self.setResult("ok")

    """
    -------------------------INIT FUNCTIONS
    """
    def config_device(self):
        """
        General device configuration
        """
        self.log("\n\/ \/ \/ \/ STARTED CONFIG!\/ \/ \/ \/\n") 
        
        if self.telnetTest is False:
            #On serial, send CR to see where we are
            self.sendDeviceCmd("")

        last_state = self.onetime_ConfigureDevice()

        #Make sure the last state is passed to the test
        #but do not pass prompts
        #TODO: this should be removed I think
        if last_state not in self.prompts:
            self.updateDeviceState(last_state)

        self.log("\n/\ /\ /\ /\ ENDED CONFIG!/\ /\ /\ /\ \n\n") 

    def setup_test_defaults(self):
        #In case setup_test is overloaded, set these here
        #NOTE: most likely will be overwritten in setup_test
        self.name = type(self).__name__
        self.full_name = type(self).__name__

        self.timeout = 300.0 #seconds

        self.config_seq = []
        self.test_seq = []

        self.actions = {}
        self.triggers = {}

        self.markers = {}
        self.markers_cfg = {}

        self.user_inp = {}

        self.prompts = []

        #Various test information
        self.info = {}

    def setup_modifiers_defaults(self):
        self.opt_RunTriggers = True
        self.opt_IgnoreStates = False
        self.opt_RandomExec = False
        self.opt_TimeCmd = False

        self.modifiers ={  # Quick modifier set
                "IGNORE_STATES" : self.e_IgnoreStates,
                "WATCH_STATES"  : self.d_IgnoreStates,
                "TRIGGER_START" : self.e_RunTriggers,
                "TRIGGER_STOP"  : self.d_RunTriggers,
                "SLEEP_RANDOM"  : self.sleepRandom,
                "RANDOM_START"  : self.e_RandomExecution,
                "RANDOM_STOP"   : self.d_RandomExecution,
                "COUNT"         : self.countTrigger,
                "TIMECMD"       : self.timeCommand
                }

        #What we need to run even if states are ignored and triggers disabled
        self.critical_modifiers = ["WATCH_STATES", "TRIGGER_START"]

        self.retval = {   
                            "config failed":    3,
                            "timeout" :         2,
                            "failed" :          1,
                            "ok":               0
                      }

    def __init__(self, test, server='169.168.56.254', port=23200, runAsTelnetTest=False):
        """
        Class init. KISS 
        NOTE: keeping default for backwards compatibility...for now
        """
        #Connection stuff
        self.server = server
        self.port = port
        self.sendendr = False

        #Add support for infinite running tests - this can be set in setup_test
        #NOTE: timeout still occurs!
        self.infiniteTest = False

        #Add support for running the tests over telnet
        self.telnetTest = runAsTelnetTest
        #For telnet we need to send just a '\r', adding a dict to make things easier
        if self.telnetTest is False:
            self.eol= { 'endr': '\r\n', 'noendr': '\n'}
        else:
            self.eol= { 'endr': '\r', 'noendr': '\r' }

        #Add support for random sleep amounts - this can be set in setup_test
        self.sleep_min = 30 #seconds
        self.sleep_max = 120 #seconds
        

        self.test_max_timeouts = 2 #How many timeouts can occur per test or per loop


        #Store counts for various triggers
        self.counter = {}
        self.counter["test_loop"] = 1
        self.counter["test_timeouts"] = self.test_max_timeouts

        self.waitPrompt_enter = 1000
        self.waitPrompt_return = 2000

        self.queue_state = queue.Queue() 
        self.queue_result = queue.Queue()

        self.queue_serread = queue.Queue()
        self.queue_serwrite = queue.Queue()


        #Start with defaults
        self.setup_test_defaults()
        self.setup_modifiers_defaults()

        #Use one main timer for all for now - note: needs default timeout value
        self.mainTimer = self.timer_startTimer(None)

        #Load the user setup
        self.setup_test(test)

        #Open the log file and print everything
        self.file_test = open(self.name + "_testresults.log", "w", buffering=1)
        self.print_test()

        self.sleep_sockWait = 0 #Just for startup
        self.mainSocket = self.sock_create()
        self.sleep_sockWait = 30 #seconds

        #For the config phase also use the cfg only markers
        self.statewatcher_markers = dict(self.markers_cfg)
        self.statewatcher_markers.update(self.markers)

        #Prepare the threads
        self.run = {}
        self.th = {}

        self.run["recv"] = True #receiver loop - used to get out of large commands
        self.th["recv"] = threading.Thread(target=self.thread_SerialRead, daemon=True)
        self.th["recv"].start()

        self.run["send"] = True #receiver loop - used to get out of large commands
        self.th["send"] = threading.Thread(target=self.thread_SerialWrite, daemon=True)
        self.th["send"].start()

        self.run["state_watcher"] = True
        self.th["state_watcher"] = threading.Thread(target=self.thread_StateWatcher, daemon=True)
        self.th["state_watcher"].start()

        #Configure the device
        self.config_device()

        #For the normal run, revert back to the normal markers
        self.statewatcher_markers = dict(self.markers)

        #See if the config failed
        res = self.getResult(block=False)
        if res is not None:
            self.cleanAll()
            exit(res)

        #Start the TEST thread
        self.run["test"] = True
        self.th["test"] = threading.Thread(target=self.thread_MyTest, daemon=True)
        self.th["test"].start()

        res = self.getResult(block=True)
        self.cleanAll()
        exit(res)


    """
    -------------------------DEVICE CONFIGURATION
    """
    def onetime_ConfigureDevice(self):
        conf_len = len(self.config_seq)
        #Quick detour
        if conf_len == 0:
            return

        conf_idx = 0
        while(conf_idx < conf_len):
            #Look for the state
            req_state = self.config_seq[conf_idx]

            #
            ##  See if we need to run some actions
            ###
            try:
                self.log("RUNNING ACTIONS:", req_state, "=", self.actions[req_state])
                for elem in self.actions[req_state]:
                    self.sendDeviceCmd(elem)
                    self.waitDevicePrompt()
                conf_idx += 1
                continue
            except KeyError:
                pass

            self.log("Looking for:", self.config_seq[conf_idx]) #idx might change
            current_state = self.getDeviceState()
            if current_state == "":
                break

            # If the required state is found 
            if req_state == current_state:
                self.log("MOVED TO STATE=", req_state)
                conf_idx += 1

            #Restart timer
            self.mainTimer = self.timer_startTimer(self.mainTimer)

                
        self.mainTimer = self.timer_stopTimer(self.mainTimer)
        return current_state

    """
    -------------------------THREADS
    """
    def thread_SerialRead(self):
        """
        Receiver thread. Parses serial out and forms things in sentences.

        TODO: re-write this. Very old code and it can be done way better 
        """
        x=b''
        eol = [ b'\n', b'\r' ] 
        while self.run["recv"] is True:
            serout = ""
            while self.run["recv"] is True:
                #Why do the timeout: the login screen displays "User:" and no endline.
                #How do you know that the device is waiting for something in this case?
                try:
                    x = self.mainSocket.recv(1)
                except socket.timeout:
                    x = b'\n'
                    break
                except OSError:
                    self.log("Reopening socket")
                    self.mainSocket = self.sock_create()
                    break #restart reading

                if not x:
                    self.log("Socket closed, reopening")
                    self.mainSocket = self.sock_create()
                    break #restart reading

                try:
                    serout += x.decode('ascii')
                except UnicodeDecodeError:
                    pass

                if x in eol:
                    break

            if(len(serout.strip()) != 0):
                self.log("DEV", serout)
                serout = serout.strip()
                self.queue_serread.put(serout)

        self.sock_close(self.mainSocket)

    def thread_SerialWrite(self):
        """
        Sender thread. Sends commands to the device.
        """
        while self.run["send"] is True:
            cmd = self.queue_serwrite.get(block=True)
            if cmd is None:
                break

            #Skip endline for y/n stuff
            #NOTE: also works for 0 len cmds for sending an CR
            if len(cmd) != 1:
                if self.sendendr is True:
                    cmd += self.eol['endr']
                else:
                    cmd += self.eol['noendr']

            try:
                #Improve handling of large commands sent to the device
                if len(cmd) > 45:
                    self.mainSocket.sendall(cmd[0:40].encode())
                    time.sleep(0.5)
                    self.mainSocket.sendall(cmd[40:].encode())
                else:
                    self.mainSocket.sendall(cmd.encode())
            except OSError:
                self.log("Waiting for socket to send stuff")
                time.sleep(0.5)
                continue

            self.log("SENT", repr(cmd))
            time.sleep(0.4)
        

    def thread_StateWatcher(self): 
        """
        STATE WATCHER: looks for the current state of the device
        """
        while(self.run["state_watcher"] is True):
            serout = self.getDeviceOutput()

            
            #Speed things up a bit
            if serout == "":
                continue

            for marker in self.statewatcher_markers:
                match = False
                if self.statewatcher_markers[marker] not in self.prompts:
                    #If marker is not a prompt, just look for it in the output
                    if marker in serout:
                        match = True
                else:
                    #If the marker is a prompt, we need to make sure we don't also
                    #consider it when it is part of a command sent to the device. So
                    #we try to see if there is something after it.
                    try:
                        if len(serout.strip().split(marker)[1]) == 0:
                            match = True
                    except IndexError:
                        continue

                if match is True:
                    current_state = self.statewatcher_markers[marker]

                    self.log("FOUND", current_state, "state in", serout)

                    #Run the critical modifiers, if any are present for the state
                    try:
                        actions = self.triggers[current_state]
                        for opt in actions:
                            if opt in self.critical_modifiers:
                                self.modifiers[opt](current_state)
                    except KeyError:
                        pass

                    #Notify everyone of the new state
                    self.updateDeviceState(current_state)

                    #Run the triggers of the state
                    if self.opt_RunTriggers is True:
                        try:
                            for act in self.triggers[current_state]:
                                if act not in self.modifiers.keys():
                                    self.sendDeviceCmd(act)
                                elif act not in self.critical_modifiers:
                                    #Run the rest of the normal modifiers, in order
                                    self.modifiers[act](current_state)
                        except KeyError:
                            pass

    def thread_MyTest(self):
        """
        ACTUAL TEST thread. Looks for states and executes stuff.
        """
        test_len = len(self.test_seq)
        test_idx = 0

        while self.run["test"] is True:
            if test_idx == test_len:
                if self.infiniteTest is True:
                    self.counter["test_loop"] += 1
                    self.counter["test_timeouts"] = self.test_max_timeouts #Reset the timeouts possible
                    self.log("GOT TO LOOP.....", self.counter["test_loop"])
                    test_idx = 0
                else:
                    break

            required_state = self.test_seq[test_idx]

            #
            ##  See if we need to wait for some user input
            ###
            try:
                self.log("\n\n\n", self.user_inp[required_state], "\n\n\n")
                #NOTE: stop timer while waiting for user input
                self.mainTimer = self.timer_stopTimer(self.mainTimer)

                input("EXECUTE ACTION AND PRESS ENTER")
                print("\nCONTINUING\n")
                test_idx += 1

                #Restart timer
                self.mainTimer = self.timer_startTimer(self.mainTimer)
                continue
            except KeyError:
                pass

            #
            ##  See if we need to run some actions
            ###
            try:
                self.log("RUNNING ACTIONS:", required_state, "=", self.actions[required_state])
                for elem in self.actions[required_state]:
                    #Run any modifiers in actions
                    try:
                        self.modifiers[elem](required_state)
                        continue
                    except KeyError:
                        pass
                    
                    #Handle RANDOM actions
                    if self.tossCoin() is True:
                        self.sendDeviceCmd(elem)
                        self.log("Waiting for prompt for elem", elem)
                        self.waitDevicePrompt()
                test_idx += 1
                continue
            except KeyError:
                pass

            #
            ##  See if we have any modifiers
            ###
            try:
                self.log("FOUND MODIFIER:", self.modifiers[required_state], "in state", required_state)

                #Needed for sleep option
                self.mainTimer = self.timer_stopTimer(self.mainTimer)

                self.modifiers[required_state](required_state)
                test_idx += 1

                #Restart timer
                self.mainTimer = self.timer_startTimer(self.mainTimer)
                continue
            except KeyError:
                pass

            self.log("Looking for:", self.test_seq[test_idx]) #idx might change
            current_state = self.getDeviceState()

            if self.opt_IgnoreStates is True:
                self.log("IGNORED STATE", current_state)
                continue

            # If the required state is found 
            if required_state == current_state:
                self.log("MOVED TO STATE=", required_state)
                test_idx += 1

                #TIMEOUT until next state
                self.mainTimer = self.timer_startTimer(self.mainTimer)

            # State changed and it isn't what we expect
            else: 
                ignore = False
                #TODO: nicer version of this! :P
                try:
                    for opt in self.modifiers.keys():
                        for trig in self.triggers[current_state]:
                            if opt == trig:
                                self.log("IGNORING STATE=", current_state)
                                ignore = True
                                break
                except KeyError:
                    pass

                if ignore is False:
                    self.log("FOUND=", current_state, ", BUT WAS LOOKING FOR:", required_state)
                    self.mytest_failed()

        self.mytest_ok()

    """
    -----------------------------------------INTERNAL APIs
    """
    def e_RunTriggers(self, state):
        #Already set, no need to do it again
        if self.opt_RunTriggers is True:
            return
        self.log("ENABLING TRIGGERS")
        self.opt_RunTriggers = True
    def d_RunTriggers(self, state):
        #Already set, no need to do it again
        if self.opt_RunTriggers is False:
            return
        self.log("DISABLING TRIGGERS")
        self.opt_RunTriggers = False

    def e_IgnoreStates(self, state):
        #Already set, no need to do it again
        if self.opt_IgnoreStates is True:
            return
        self.log("IGNORING STATES")
        self.opt_IgnoreStates = True
        if self.telnetTest is True:
            #Only on telnet, close the socket now, as this is probably a reboot
            self.sock_close(self.mainSocket)

    def d_IgnoreStates (self, state):
        #Already set, no need to do it again
        if self.opt_IgnoreStates is False:
            return
        self.log("WATCHING STATES")
        self.opt_IgnoreStates = False

    def e_RandomExecution(self, state):
        self.log("RANDOM EXECUTION")
        self.opt_RandomExec = True

    def d_RandomExecution(self, state):
        self.log("STOP RANDOM EXECUTION")
        self.opt_RandomExec = False

    def countTrigger(self, state):
        try:
            self.counter[state] += 1
        except KeyError:
            self.counter[state] = 1

        self.log("COUNTING for \'" + state + "\'...got to ", self.counter[state])
        #Display all counting stats everytime:
        for elem in self.counter:
            self.log("COUNT FOR", elem, "is", self.counter[elem])

    def timeCommand(self, state):
        self.opt_TimeCmd = True

    def sleepRandom(self, state):
        duration = random.randint(self.sleep_min, self.sleep_max)
        self.log("ZzzzZZzzzzzzZzzzz....(", duration, "seconds )....")
        time.sleep(duration)
        self.log("....WAKE UP!")

    def tossCoin(self):
        if self.opt_RandomExec is False:
            return True
        else:
            ret = random.choice([True, False])
            self.log("Random coin toss showed", ret)
            return ret

    def getDeviceOutput(self):
        """
        Wrapper over serial receive queue. Blocks until data is available.

        Returns "" if queue is closing.
        """
        serout = self.queue_serread.get(block=True)
        self.queue_serread.task_done()
        if serout is None:
            return ""
        else:
            return serout

    def sendDeviceCmd(self, cmd):
        """
        Wrapper over serial send queue.
        """
        self.queue_serwrite.put(cmd)


    def getDeviceState(self, blockQueue=True):
        """
        Wrapper over state queue. Blocks until data is available.

        Returns "" if queue is closing.
        """
        while True:
            try:
                state = self.queue_state.get(block=blockQueue)
                self.queue_state.task_done()
                if state is None:
                    continue
                else:
                    return state
            except queue.Empty:
                continue

    def waitDevicePrompt(self):

        wait1_enter = self.waitPrompt_enter
        wait2_return = self.waitPrompt_return

        if self.opt_TimeCmd is True:
            startOfPromptWait = datetime.datetime.now()

        while True:
            if self.opt_IgnoreStates is True:
                self.log("Ignore states is set, canceling prompt wait")
                break

            state = self.getDeviceState(False)
            if state in self.prompts:
                self.log("Found prompt!")
                break
            else:
                self.updateDeviceState(state)

            #First thing, let's try to send a CR
            wait1_enter -=1
            if wait1_enter == 0:
                self.sendDeviceCmd("")
                self.log("NO PROMPT FOUND! Trying a CR...")
                wait1_enter = -1 #But only once

            #If that does not work, let's try to continue
            #otherwise we will get a timeout anyway
            wait2_return -=1
            if wait2_return == 0:
                self.log("NO PROMPT FOUND! TRYING TO CONTINUE...")
                break

            time.sleep(0.2)

        if self.opt_TimeCmd is True:
            self.opt_TimeCmd = False
            endOfPromptWait = datetime.datetime.now()
            self.log("Command took", str(endOfPromptWait - startOfPromptWait))

    def waitDeviceState(self, state):
        while(self.getDeviceState() != state):
            time.sleep(0.1)

    def updateDeviceState(self, state):
        """
        Wrapperr over state queue.
        """
        self.queue_state.put(state)

    def getResult(self, block=True):
        """
        Wrapper over result queue. Blocks until data is available.
        """
        ret = None
        try:
            res = self.queue_result.get(block)
        except queue.Empty:
            res = None

        if res is not None:
            self.queue_result.task_done()
            self.log("GOT RESULT:", res)
            try:
                ret = self.retval[res]
                self.log("RETURNING:", ret)
            except KeyError:
                self.log("RET VALUE UNKNOWN! Update retval option!")
                ret = -98
        elif block is True:
            self.log("RESULT QUEUE FAILED! GENERIC ERROR!")
            ret = -99

        return ret
    
    def setResult(self, res):
        """
        Wrapper over result queue. Does some filtering of the final message.
        """
        try:
            self.queue_result.put_nowait(res)
        except queue.QueueFull:
            print("FAILED TO SET RESULT")
            pass

    def timer_startTimer(self, timer):
        """
        Starts or restarts a timer using the class options (timeout and mytest_timeout)
        """
        try:
            if timer is not None:
                timer.cancel()
                del timer
            timer = threading.Timer(self.timeout, self.mytest_timeout)
            timer.start()
        except UnboundLocalError:
            self.log("ERROR starting timer!")
            timer = None

        return timer

    def timer_stopTimer(self, timer):
        """
        Just stops a timer
        """
        try:
            if timer is not None:
                timer.cancel()
                del timer
        except UnboundLocalError:
            self.log("ERROR stopping timer!")
            timer = None
            pass

        return None

    def sock_create(self):
        if self.telnetTest is True and self.sleep_sockWait != 0:
            #On telnet it might close before the IGNORE STATES part
            self.e_IgnoreStates(None)
            self.d_RunTriggers(None)
            time.sleep(self.sleep_sockWait) #wait a bit before restarting connection

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.log("Opening socket")
        connected = False
        while connected is False:
            try:
                s.connect((self.server, self.port))
                connected = True
            except OSError:
                time.sleep(5)
                self.log("Still waiting...")
                pass
        s.setblocking(0)
        s.settimeout(2) #seconds
        self.log("Socket online") 
        
        #We might have missed something on serial
        #On telnet this is important
        self.opt_IgnoreStates = False
        self.opt_RunTriggers = True
        return s

    def sock_close(self, s):
        if s is not None:
            self.log("Closing socket")
            s.close()
            s = None

    def logNoPrint(self, *args):
        outtext = ""
        for elem in args:
            outtext += str(elem)
            outtext += " "

        try:
            self.file_test.write(str(datetime.datetime.now()) + ' - ' + outtext + "\n")
            return outtext
        except ValueError:
            return ""

    def log(self, *args):
        print(str(datetime.datetime.now()), self.logNoPrint("+++>", *args))

    def print_test(self):
        self.file_test.write(self.name + "\n\n")
        self.file_test.write(self.full_name + "\n\n")
        for elem in self.info:
            if elem == "version":
                self.file_test.write(elem + " - " + str(self.info[elem][0]) + "\n")
            else:
                self.file_test.write(elem + " - " + str(self.info[elem]) + "\n")

        self.file_test.write("\n\n")

        self.file_test.write("MARKERS:\n")
        self.file_test.write(str(self.markers) + "\n")
        self.file_test.write("MARKERS CFG:\n")
        self.file_test.write(str(self.markers_cfg) + "\n")
        self.file_test.write("TRIGGERS:\n")
        self.file_test.write(str(self.triggers) + "\n")
        self.file_test.write("CONF SEQ:\n")
        self.file_test.write(str(self.config_seq) + "\n")
        self.file_test.write("TEST SEQ:\n")
        self.file_test.write(str(self.test_seq) + "\n")
        self.file_test.write("USER_INP\n")
        self.file_test.write(str(self.user_inp) + "\n")
        self.file_test.write("ACTIONS:\n")
        self.file_test.write(str(self.actions) + "\n")

        self.file_test.write("RUN TRIGGERS=" + str(self.opt_RunTriggers) + "\n")
        self.file_test.write("IGNORE STATES=" + str(self.opt_IgnoreStates) + "\n")

        self.file_test.write("\n\nTEST START:\n\n")

    def cleanAll(self):
        print(self.run)
        for elem in self.run:
            self.run[elem] = False
            print("Ended", elem)

        self.queue_state.put(None)
        self.queue_serread.put(None)
        self.queue_serwrite.put(None)

        print(self.th)
        #NOTE: result watcher is not in list!
        for thread in self.th:
            print("Joining with", thread)
            self.th[thread].join()
            print("Joined with", thread)

        print("CLOSING FILE")
        self.file_test.close()
        print("CLOSED FILE")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ultra-light test framework")

    parser.add_argument('test', help='YAML test file to run')
    parser.add_argument('--server', help='IP to telnet to',
            default='localhost')
    parser.add_argument('--port', help='Port to telnet to',
            type=int, default=3000)
    parser.add_argument('--telnet', help='Run test over telnet to device',
            action='store_true')

    args = parser.parse_args()

    test = Overwatcher(args.test, server=args.server, port=args.port, runAsTelnetTest=args.telnet)


