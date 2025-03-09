#!/usr/bin/env python

"""

Adapted to the go-e controller by Martin Große in 2024.

Created by Ralf Zimmermann (mail@ralfzimmermann.de) in 2020.
This code and its documentation can be found on: https://github.com/RalfZim/venus.dbus-fronius-smartmeter
Used https://github.com/victronenergy/velib_python/blob/master/dbusdummyservice.py as basis for this service.
Reading information from the Fronius Smart Meter via http REST API and puts the info on dbus.
"""

import dbus 
import atexit


import platform 
import logging
import sys
import os
import sys
if sys.version_info.major == 2:
  import gobject  
else:
  from gi.repository import GLib as gobject

import sys
import requests # for http GET
import configparser # for config/ini file
try:
  import thread   # for daemon = True  / Python 2.x
except:
  import _thread as thread   # for daemon = True  / Python 3.x

# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '../ext/velib_python'))
from vedbus import VeDbusService

path_UpdateIndex = '/UpdateIndex'


class DbusGoeControllerService:
  def __init__(self, servicename, deviceinstance, paths, productname='Go-E Smart Meter', connection='go-e controller Smart Meter service'):
    config = self._getConfig()
    self._accessType = config['DEFAULT']['AccessType']
    self._host = config['DEFAULT']['Host'];
    if self._accessType == 'ModBus':
       logging.info("Access via Modbus")
    else:
       logging.info("Access via Http")
       self._url = "http://%s/api/status?filter=isv,ccp,usv,cec,fwv" % (self._host)
    self._SetL1 = config['DEFAULT'].getint('PhaseL1',1);
    self._SwitchL2L3 = config['DEFAULT'].getboolean('SwitchL1L2',False);
    
    self._dbusservice = VeDbusService(servicename,register=False)
    self._paths = paths

    logging.debug("%s /DeviceInstance = %d" % (servicename, deviceinstance))

    # Create the management objects, as specified in the ccgx dbus-api document
    self._dbusservice.add_path('/Mgmt/ProcessName', __file__)
    self._dbusservice.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self._dbusservice.add_path('/Mgmt/Connection', connection)

    # Create the mandatory objects
    self._dbusservice.add_path('/DeviceInstance', deviceinstance)
    self._dbusservice.add_path('/ProductId', 16) # value used in ac_sensor_bridge.cpp of dbus-cgwacs
    self._dbusservice.add_path('/ProductName', productname)
    self._dbusservice.add_path('/FirmwareVersion', 0.1)
    self._dbusservice.add_path('/HardwareVersion', 0)
    self._dbusservice.add_path('/Connected', 1)
    self._dbusservice.add_path('/Latency', None)

    for path, settings in self._paths.items():
      self._dbusservice.add_path(
        path, settings['initial'], gettextcallback=settings['textformat'], writeable=True, onchangecallback=self._handlechangedvalue)

    self._dbusservice.register()

    gobject.timeout_add(config['DEFAULT'].getint('Rate',1000), self._update) # pause 1000ms before the next request
    
    # add _signOfLife 'timer' to get feedback in log every 5minutes
    # 
    # if config['DEFAULT'].getint('SignOfLifeLog',0)>0:
    # gobject.timeout_add(config['DEFAULT'].getint('SignOfLifeLog')*60*1000, self._signOfLife)

  def _getConfig(self):
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    return config

  def _signOfLife(self):
    logging.info("--- Start: sign of life ---")
    logging.info("Last _update() call: %s" % (self._lastUpdate))
    logging.info("Last '/Ac/Power': %s" % (self._dbusservice['/Ac/Power']))
    logging.info("--- End: sign of life ---")
    return True

  def _setCurrent(self, current, power):
    if power>0 and current<0:
       return current*-1.0
    elif power<0 and current>0:
       return current*-1.0
    else:
       return current

  def _update(self):
    try:
      meter_url = "http://192.168.8.181/api/status?filter=isv,ccp,usv,cec,fwv"

      
      meter_r = requests.get(url=self._url) # request data from the Fronius PV inverter
      meter_data = meter_r.json() # convert JSON data
#        fwv = (meter_data['fwv'])
#      self._dbusservice.add_path('/FirmwareVersion', fwv )
#      meter_model = meter_data['host']
#      if meter_model == 'Smart Meter 63A-1':  # set values for single phase meter
#        meter_data['Body']['Data']['Voltage_AC_Phase_2'] = 0
#        meter_data['Body']['Data']['Voltage_AC_Phase_3'] = 0
#        meter_data['Body']['Data']['Current_AC_Phase_2'] = 0
#        meter_data['Body']['Data']['Current_AC_Phase_3'] = 0
#        meter_data['Body']['Data']['PowerReal_P_Phase_2'] = 0
#        meter_data['Body']['Data']['PowerReal_P_Phase_3'] = 0
#      print("Power=",round((meter_data['ccp'][0]),2))

      self._dbusservice['/Ac/Power'] = round((meter_data['ccp'][1]),2) # positive: consumption, negative: feed into grid
      
      #print("AC-Power",round((meter_data['ccp'][1]),2))
      
      if self._SetL1==2:      
        #print("AC-Power L1",round((meter_data['isv'][1]['p']),2))
        power = round((meter_data['isv'][1]['p']),2)
        self._dbusservice['/Ac/L1/Voltage'] = round((meter_data['usv'][0]['u2']),2)
        self._dbusservice['/Ac/L1/Current'] = self._setCurrent(round((meter_data['isv'][1]['i']),2), power)
        self._dbusservice['/Ac/L1/Power'] = power
        if self._SwitchL2L3==True:
          #print("AC-Power L2",round((meter_data['isv'][2]['p']),2))
          #print("AC-Power L3",round((meter_data['isv'][0]['p']),2))
          power = round((meter_data['isv'][2]['p']),2)
          self._dbusservice['/Ac/L2/Voltage'] = round((meter_data['usv'][0]['u3']),2)
          self._dbusservice['/Ac/L2/Current'] = self._setCurrent(round((meter_data['isv'][2]['i']),2), power)
          self._dbusservice['/Ac/L2/Power'] = power
          power = round((meter_data['isv'][0]['p']),2)
          self._dbusservice['/Ac/L3/Voltage'] = round((meter_data['usv'][0]['u1']),2)
          self._dbusservice['/Ac/L3/Current'] = self._setCurrent(round((meter_data['isv'][0]['i']),2), power)
          self._dbusservice['/Ac/L3/Power'] = power
        else:
          print("AC-Power L2",round((meter_data['isv'][0]['p']),2))
          print("AC-Power L3",round((meter_data['isv'][2]['p']),2))
          power = round((meter_data['isv'][0]['p']),2)
          self._dbusservice['/Ac/L2/Voltage'] = round((meter_data['usv'][0]['u1']),2)
          self._dbusservice['/Ac/L2/Current'] = self._setCurrent(round((meter_data['isv'][0]['i']),2), power)
          self._dbusservice['/Ac/L2/Power'] = power
          power = round((meter_data['isv'][2]['p']),2)
          self._dbusservice['/Ac/L3/Voltage'] = round((meter_data['usv'][0]['u3']),2)
          self._dbusservice['/Ac/L3/Current'] = self._setCurrent(round((meter_data['isv'][2]['i']),2), power)
          self._dbusservice['/Ac/L3/Power'] = power
      elif self._SetL1==3:     
        power = round((meter_data['isv'][2]['p']),2)
        self._dbusservice["/Ac/L1/Voltage"] = round((meter_data['usv'][0]['u3']),2)
        self._dbusservice['/Ac/L1/Current'] = self._setCurrent(round((meter_data['isv'][2]['i']),2), power)
        self._dbusservice['/Ac/L1/Power'] = power
        if self._SwitchL2L3==True:
          power = round((meter_data['isv'][1]['p']),2)
          self._dbusservice['/Ac/L2/Voltage'] = round((meter_data['usv'][0]['u2']),2)
          self._dbusservice['/Ac/L2/Current'] = self._setCurrent(round((meter_data['isv'][1]['i']),2), power)
          self._dbusservice['/Ac/L2/Power'] = power
          power = round((meter_data['isv'][0]['p']),2)
          self._dbusservice['/Ac/L3/Voltage'] = round((meter_data['usv'][0]['u1']),2)
          self._dbusservice['/Ac/L3/Current'] = self._setCurrent(round((meter_data['isv'][0]['i']),2), power)
          self._dbusservice['/Ac/L3/Power'] = power
        else:
          power = round((meter_data['isv'][0]['p']),2)
          self._dbusservice['/Ac/L2/Voltage'] = round((meter_data['usv'][0]['u1']),2)
          self._dbusservice['/Ac/L2/Current'] = self._setCurrent(round((meter_data['isv'][0]['i']),2), power)
          self._dbusservice['/Ac/L2/Power'] = power
          power = round((meter_data['isv'][1]['p']),2)
          self._dbusservice['/Ac/L3/Voltage'] = round((meter_data['usv'][0]['u2']),2)
          self._dbusservice['/Ac/L3/Current'] = self._setCurrent(round((meter_data['isv'][1]['i']),2), power)
          self._dbusservice['/Ac/L3/Power'] = power
      else:
        power = round((meter_data['isv'][0]['p']),2)
        self._dbusservice["/Ac/L1/Voltage"] = round((meter_data['usv'][0]['u1']),2)
        self._dbusservice['/Ac/L1/Current'] = self._setCurrent(round((meter_data['isv'][0]['i']),2), power)
        self._dbusservice['/Ac/L1/Power'] = power        
        if self._SwitchL2L3==True:
          power = round((meter_data['isv'][2]['p']),2)
          self._dbusservice['/Ac/L2/Voltage'] = round((meter_data['usv'][0]['u3']),2)
          self._dbusservice['/Ac/L2/Current'] = self._setCurrent(round((meter_data['isv'][2]['i']),2), power)
          self._dbusservice['/Ac/L2/Power'] = power
          power = round((meter_data['isv'][1]['p']),2)
          self._dbusservice['/Ac/L3/Voltage'] = round((meter_data['usv'][0]['u2']),2)
          self._dbusservice['/Ac/L3/Current'] = self._setCurrent(round((meter_data['isv'][1]['i']),2), power)
          self._dbusservice['/Ac/L3/Power'] = power
        else:
          power = round((meter_data['isv'][1]['p']),2)
          self._dbusservice['/Ac/L2/Voltage'] = round((meter_data['usv'][0]['u2']),2)
          self._dbusservice['/Ac/L2/Current'] = self._setCurrent(round((meter_data['isv'][1]['i']),2), power)
          self._dbusservice['/Ac/L2/Power'] = power
          power = round((meter_data['isv'][2]['p']),2)
          self._dbusservice['/Ac/L3/Voltage'] = round((meter_data['usv'][0]['u3']),2)
          self._dbusservice['/Ac/L3/Current'] = self._setCurrent(round((meter_data['isv'][2]['i']),2), power)
          self._dbusservice['/Ac/L3/Power'] = power
        
#      self._dbusservuce['/ac/L1/PowerFactor'] = round((meter_data['isv'][0]['f']),3)
#      self._dbusservice['/ac/L2/PowerVactor'] = round((meter_data['isv'][1]['f']),3)
#      self._dbusservice['/ac/L3/PowerFactor'] = round((meter_data['isv'][2]['f']),3)
      self._dbusservice['/Ac/Energy/Forward'] = round(((meter_data['cec'][0][0])/1000),4)
      self._dbusservice['/Ac/Energy/Reverse'] = round(((meter_data['cec'][0][1])/1000),4)
#      logging.info("House Consumption: {:.0f}".format(meter_consumption))
    except:
      logging.info("WARNING: Could not read from Go-E Controller SmartMeter")
      #self._dbusservice['/Ac/Power'] = 1  # TODO: any better idea to signal an issue?
    # increment UpdateIndex - to show that new data is available
    index = self._dbusservice[path_UpdateIndex] + 1  # increment index
    if index > 255:   # maximum value of the index
      index = 0       # overflow from 255 to 0
    self._dbusservice[path_UpdateIndex] = index
    return True

  def _handlechangedvalue(self, path, value):
    logging.debug("someone else updated %s to %s" % (path, value))
    return True # accept the change

def end():
  print('Close ... start');
  
  print('Close ... end');

def main():
  atexit.register(end)
  logging.basicConfig(filename=("%s/goeController.log" % (os.path.dirname(os.path.realpath(__file__)))), 
                        filemode='w', 
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S', 
                        level=logging.INFO) # use .INFO for less logging
  thread.daemon = True # allow the program to quit

  from dbus.mainloop.glib import DBusGMainLoop
  # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
  DBusGMainLoop(set_as_default=True)

  #formatting
  def _kwh(p, v):
   return str("%.2f" % v) + "kWh"

  def _a(p, v):
   return str("%.1f" % v) + "A"

  def _w(p, v):
   return str("%i" % v) + "W"

  def _v(p, v):
   return str("%.2f" % v) + "V"

  def _hz(p, v):
   return str("%.4f" % v) + "Hz"

  def _n(p, v):
   return str("%i" % v)

  pvac_output = DbusGoeControllerService(
    servicename='com.victronenergy.grid.mymeter',
    deviceinstance=0,
    paths={
      '/Ac/Power': {'initial': 0, 'textformat': _w},
      '/Ac/L1/Voltage': {'initial': 0, 'textformat': _v},
      '/Ac/L2/Voltage': {'initial': 0, 'textformat': _v},
      '/Ac/L3/Voltage': {'initial': 0, 'textformat': _v},
      '/Ac/L1/Current': {'initial': 0, 'textformat': _a},
      '/Ac/L2/Current': {'initial': 0, 'textformat': _a},
      '/Ac/L3/Current': {'initial': 0, 'textformat': _a},
      '/Ac/L1/Power': {'initial': 0, 'textformat': _w},
      '/Ac/L2/Power': {'initial': 0, 'textformat': _w},
      '/Ac/L3/Power': {'initial': 0, 'textformat': _w},
#      '/Ac/L1/Frequency' : {"initial": None, "textformat": _hz},
#      '/Ac/L2/Frequency' : {"initial": None, "textformat": _hz},
#      '/Ac/L3/Frequency' : {"initial": None, "textformat": _hz},
#      '/ac/L1/PowerFactor': {'initial': None, 'textformat': _n},
#      '/ac/L2/PowerFactor': {'initial': None, 'textformat': _n},
#      '/ac/L3/PowerFactor': {'initial': None, 'textformat': _n}, 
      '/Ac/Energy/Forward': {'initial': 0, 'textformat': _kwh}, # energy bought from the grid
      '/Ac/Energy/Reverse': {'initial': 0, 'textformat': _kwh}, # energy sold to the grid
      path_UpdateIndex: {'initial': 0, 'textformat': _n},
    })

  logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
  mainloop = gobject.MainLoop()
  mainloop.run()

if __name__ == "__main__":
  main()
