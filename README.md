# overwatcher
Ultra-lightweight automated testing framework for CLIs.

## Design ideas:
- **KEEP IT SIMPLE!!!!** The framework itself should be in a single file, and each test in a file. The framework does not
  need to know anything about the device, just runs stuff and keeps an eye out for other stuff.
- **log everything important!** The log file can look a bit intimidating, but after looking at a log file, you can
  understand what happened and why. This is why logging levels were not introduced for now, just dump everything in a
  file and use the search function :)
- **make sure the results are reproducible!** This is the reason for introducing the versioning and keeping everything
  in just two files. It is easier to make sure that the tests work in the same way even after a while...or force a
  review of the test if something major changes.

## Current state:
- tested on both serial connection (using ser2net) and telnet straight to the device. Depending on the test, the same
  test might run on both without any changes.
- tests can be written as python classes or as YAML files
- tests can run in a finite time or cycle forever (both on serial and telnet). There is a watchdog implemntation which
  does not let the test freeze. In case of a timeout, some actions to recover the device can be attempted.
- outcome is a single log file containing all the test information (including version, parameters and options) and the
  entire flow (including device output). The framework also returns a different code based on the test results, so it
  can be used in bash scripts.

## The future:
- there will be no 'device-specific dictionary', as this can complicate things with the "reproducible" part. The current
  idea for solving this is to implement regular expression hadling for markers and writing tests so that the device
  specific parts are left out. The biggest problem can be on serial, but careful marker choice might solve this
  (hopefully). This will be seen in time.
- add more randomness to tests. There is already an option to randomly run commands or to sleep a random amount of time,
  but this needs to be expanded. Who knows what a simple test might uncover :)

## Anatomy of a test
The basic idea: the test defines a list of states (markers) and actions that have to be run. This list is walked on
element by element: when a state is the next element, overwatcher waits for the marker that describes that state, 
when an action/option is the next element, it just runs that action/option. If overwatcher is looking for one state and
a different one is seen, the test fails.

0. *Test information* This "header" contains a full test description and it is dumped in the test log, so more stuff can
   be easily added. There are two mandatory fields: 'version' (which needs to be kept in a reverse order - only the first
   one is dumped in the log) and 'overwatcher revision required' (this is still WIP, but it should have the format in the
   example. If the framework revision does not match this field, there will be a warning when starting the test). The 
   'serial only' field can be added and will generate a warning when tests are run over telnet; if it is not present, it
   is assumed to be False.
1. *MARKERS* These are text elements that overwatcher pays attention to. Can be used to trigger actions immediatly when
   seen (example: see User -> send username) or to define the actual test flow.
   Be careful when choosing a marker, as the test fails if the marker found does not match the one expected during the
   test run. There are two exceptions to this rule: markers that have only OPTIONS in their triggers and prompts (see
   below). The first exception was introduced to be able to do some small tasks (ex: count a string that appears from time
   to time). Prompts are consumed by running actions.
2. *PROMPTS* Thse are string that are expected after a command is sent to the device. Why? Because we might run into 
   commands that take a while to run and the test should not keep pushing stuff to the device while it is blocked.
   For now, this is not blocking; if the prompt is not seen in a while, overwatcher tries to send a CR (only on serial); 
   if the prompt still does not appear, it tries to continue the test (the timeout will stop it anyway if the device is blocked)
3. *TRIGGERS* Triggers are automatic actions that are run when a marker is seen. These actions can include sending device 
   commands or setting overwatcher options. Please note that these triggers do not take into account the test flow...if
   a marker appears, they are just run. Also triggers do not wait for prompts, the elements are sent with a small delay.
   NOTE: triggers can contain options. There are critical options which are run even if triggers are disabled (see
   below).
4. *ACTIONS* Actions are commands that will be run during the test flow. Unlike triggers, they are not automatic, they 
   need to be added to the test flow below to be run. After each element of the list of actions is run, overwatcher waits
   for a prompt before sending the next one.
   NOTE: actions can contain options.
5. *INITIAL CONFIGURATION* This is a sequence identical to the test, but it is only run once when starting the test.
   It can be used to do some initial sets. The recommanded way to start this is with a marker for a known state...the 
   config blocks until it reaches that state (either via triggers or manually) and then it runs the configuration 
   actions from a known state. There is a watchdog in effect while doing the config...if it take too long, the test
   fails. The timeout value is configurable.
6. **TEST** This is a series of markers, actions and options that are expected and run in the given order. The actual 
   test can be single run (go through it and stop) or infinite (run forever). Take this into account and use the 
   configuration sequence above for initial configuration. To further enhance the functionality you can use the options 
   below. The same watchdog is in effect while running the test. It is reset after passing to a new state. The timeout
   value is configurable.

## Options
**NEED a new name for these, as they can be confused with the ones below :)**
These are a sort of "special actions" which control and change the test flow.
- IGNORE\_STATES - if a marker is seen, ignore the transition to that state. This 
  is mostly used in reboots to handle if a new login screen appears. It also cancels
  any prompt waits in effect. On telnet it closes the socket.
- WATCH\_STATES - allow transitions to a found state. THIS IS A CRITICAL OPTION and it is
  set when found in a trigger, even if triggers are disabled.
- TRIGGER\_START - run triggers on markers again. THIS IS A CRITICAL OPTION and it is
  set when found in a trigger, even if triggers are disabled.
- TRIGGER\_STOP - do not run triggers on markers anymore.
- SLEEP\_RANDOM - sleep a random amount of time. The random interval is controlled by 
  sleepMin and sleepMax (see below).
- RANDOM\_START - begins a block of randomly executed commands. Before sending each
  command to the device, a random draw is made; if it is true, the command is sent, 
  otherwise it is discarded and the test moves on. This can be used to add some randomness
  to a test.
- RANDOM\_STOP - stop the random draw. All commands are sent to the device.   
 -COUNT - Simply counts how many times a marker appears during the test. All counts are
  displayed once one is incremented (increases the log file, but handels infinte tests
  easier). NOTE: there are two permanent counts in each test: the number of loops run (if it
  is infinite) and how many timeouts are left per loop.

## Configurable test options
These are just parameters that control the inner workings of the test:
- sleep\_min and sleep\_max: interval in which SLEEP\_RANDOM generates values
- sleep\_sockWait: on telnet, how much to wait before trying to re-open the socket
- infiniteTest: run the test in a loop. When the final state/action/option is reached, starts from the first one again.
  The configuration is not run again.
- timeout: how long to wait when looking for a state. NOTE: this is not influenced by the prompt or by running commands.
- test\_max\_timeouts - how many timeouts can occur per test loop
