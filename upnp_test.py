'''
Created on 25.01.2015

@author: mw
'''

import unittest
from plugins.denon import Denon
from plugins.denon.upnp import UPNP 
import pprint
   
class Test(unittest.TestCase):

    def __item(self, value, caller):
        # ersatzroutine für das setzen der item werte
        print('DENON: _update_status: value: [{0}]: caller: [{1}]'.format(value,caller))

    def setUp(self):
        self.d = Denon('','192.168.2.27')
        self.d._listenItems = {'0szLine' : self.__item,
                          '1MasterVolume' : self.__item, '1Power': self.__item, '1Mute' : self.__item, '1InputFuncSelect' : self.__item, '1SurrMode' : self.__item,
                          '2MasterVolume' : self.__item, '2Power': self.__item, '2Mute' : self.__item, '2InputFuncSelect' : self.__item, '2SurrMode' : self.__item,
                          '0errorstatus' : self.__item, '0DeviceZones' : self.__item, '0MacAddress' : self.__item, '0ModelName' : self.__item
                          }
        self._zoneXMLCommandURI = {'0' :'/goform/formNetAudio_StatusXml.xml', '1' : '/goform/formMainZone_MainZoneXmlStatus.xml', '2': '/goform/formZone2_Zone2XmlStatus.xml'}                        
        self.u = UPNP()
    
    # hier alles zum testen der Interfaces usw.   
    def _test_upnp_dicovery(self):
        i=0
        while i<1:
            self.u.ssdp_scan(ssdpTimeout=5)
            i=i+1
        
    def test_upnp_find_services(self):
        upnpServices = self.u.upnp_find_sevices()
        #pp.pprint(upnpServices['192.168.2.12'])   
        
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
