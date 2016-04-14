'''
General configuration loader. Supports loading values from a file or reading them
from the user (with or without a default).

NOTE: see example.cfg for usage
WARNINGS:
    -when giving hex or ints as strings, enclose them in ""
    -when giving dictionary values, enclose the entire dictinary in ""

Features:
    -supports lists, ranges and dictionaries
    -tries to guess some basic types

TESTS:
    -example.cfg contains basic tests for the implemented types:
        -int, float, string
        -list, dictionary, range
        -values with/without a type
        -values with/without a default
        -values with/without a value
        -reading list, dictionary, range
TODO:
    -support for custom types
    -support for save
    -better way to turn autocomplete off
    -autocomplete for all types?

Changelog:
    09.12.2014  - added bool type(DONE) and filename (WIP)
                - added dynamic calling of user define functions
                - added autocompletion of filenames
                - changed the dictionaries to OrderedDict (so items keep their order)
'''
import yaml
import readline
import glob
import collections

#See experimental folder for source
def complete(text, state):
    return (glob.glob(text+'*')+[None])[state]
#TODO: better way to do this?
def uncomplete(text, state):
    return None

class Config():
    def __init__(self, config_file=None, user_variables=None, custom_types=None):
        #
        ## Parse and close the file
        #
        if config_file is not None:
            cfgFile = open(config_file, "r")
            parsedData = list(yaml.safe_load_all(cfgFile))[0]
            cfgFile.close()
        else:
            parsedData = []

        var_val = collections.OrderedDict()
        var_def = collections.OrderedDict()
        var_typ = collections.OrderedDict()

        #
        ## Parse the list
        #
        for varName in parsedData:
            varData = parsedData[varName]

            if varData is not None:
                typ = parsedData[varName].get("type")
                val = parsedData[varName].get("value")
                dva = parsedData[varName].get("default")

                var_val[varName] = self.createVar(typ, val)
                var_def[varName] = self.createVar(typ, dva)

                if typ is None:
                    if val is not None:
                        typ = type(self.guessType(val)).__name__
                    elif dva is not None:
                        typ = type(self.guessType(dva)).__name__

                var_typ[varName] = typ
            else:
                var_val[varName] = None
                var_def[varName] = None
                var_typ[varName] = None


        #Append the user variables
        if user_variables is not None:
            for var in user_variables:
                var_val[var[0]] = None
                var_typ[var[0]] = var[1]
                var_def[var[0]] = var[2]

        #
        ## Read unknown values
        #
        for valName in var_val:
            print(valName, var_val[valName])

        for varName in var_val:
            if var_val[varName] is None:
                print(varName)
                var_val[varName] = self.userRead(varName,
                                                 var_typ[varName],
                                                 var_def[varName])

        #
        ## DEBUG
        #
        for varName in var_val:
            print(varName, "=", var_val[varName],"(def=", var_def[varName], ")")

        #
        ## Create the variables in the class
        #
        for varName in var_val:
            setattr(self, varName, var_val[varName])

    '''
    This set of functions can be expanded
    '''
    def process_bool(self, rawValue):
        if rawValue == "True" or rawValue == "true":
            return True
        elif rawValue == "False" or rawValue == "false":
            return False
        else:
            return None

    def process_list(self, rawValue):
        output = []
        elems = rawValue.split(",")

        for elem in elems:
            output.append(self.guessType(elem.strip()))

        return output

    def process_dict(self, rawValue):
        output = {}
        elems = rawValue.split(",")

        for elem in elems:
            name = elem.split(":")[0].strip()
            value = elem.split(":")[1].strip()

            output[name] = self.guessType(value)

        return output

    def process_range(self, rawValue):
        start = int(rawValue.split("-")[0])
        end = int(rawValue.split("-")[1])

        return range(start, end)

    def process_filename(self, rawValue):
        return str(rawValue)

    '''
    Fixed functions, shoud not need changes (not even bugfixes :P)
    '''

    '''
    Creates a variable based on type. Will try to guess if no type is available.
    '''
    def createVar(self, varType, rawValue):
        #No processing needed for None
        if rawValue is None:
            return None

        #No type, try to guess
        if varType is None or varType == "any":
            return self.guessType(rawValue)

        if varType == "int":
            return int(rawValue)
        elif varType == "float":
            return float(rawValue)
        elif varType == "string" or varType == "str":
            return str(rawValue)
        else:
            #NOTE: added dynamic calling of user defined functions
            userDefFunc = getattr(self, "process_" + varType)
            if userDefFunc is None:
                raise NotImplementedError("Please provide a parser for " + varType)
            return userDefFunc(rawValue)

    '''
    Tries to guess the type of a variable. For now this is limited to some
    basic, most-used types, as I assume that more complex types will get a
    "type" label in the config file. If the user is lazy, he will get an error :P
    '''
    def guessType(self, rawValue):
        if type(rawValue).__name__ != "str":
            return rawValue # No need to change it, it already has a definit type

        if "." in rawValue:
            try:
                return float(rawValue)
            except ValueError:
                pass
        try:
            return int(rawValue)
        except ValueError:
            pass

        #Return as string if nothing works
        return str(rawValue)

    '''
    Read a value from the user. If we have a default, the user can entering
    something. If we don't have a default, he must keep entering until he gets
    the type right.
    '''

    def userRead(self, varName, varType, varDef):
        print(varName, varType, varDef)
        rawVal = None
        if varType is None:
            varType = "any"

        #Read until a good value is given
        while rawVal is None:
            #Display the var name, type and def(if any)
            if varDef is None:
                displayedString = varType + " - " + varName + " = "
            else:
                displayedString = varType + " - " + varName + " (def=" + str(varDef) + ") = "

            #Read with autocomplete (only for filenames for now)
            if varType == "filename":
                readline.set_completer_delims(' \t\n;')
                readline.parse_and_bind("tab: complete")
                readline.set_completer(complete)
            else:
                readline.set_completer(uncomplete)
            rawVal = input(displayedString)

            #What happens if the user only pushed ENTER?
            if rawVal == "":
                #If there is a default value, use that
                rawVal = varDef
                #If there is no default, empty strings are not accepted
                if varDef is None:
                    continue

            #See if the value is correct
            try:
                rawVal = self.createVar(varType, rawVal)
            except:
                rawVal = None

        return rawVal
