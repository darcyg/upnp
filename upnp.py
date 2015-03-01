#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#
# Copyright (C) 2015 Michael Würtenberger
#
# UPNP Service for Plugins for sh.py
#
# v 0.2
#
# is not a real upnp client implementation, but installs the necessary service to get
# an standard environment to work, tested on a simple bases !

import socket
import logging
import xml.etree.ElementTree as et
import lib.www
import threading
import pprint
from ast import NodeTransformer

logger = logging.getLogger('UPNP')

class UPNP(lib.www.Client):

    # Initialize connection to receiver
    def __init__(self):
        
        self._fetchUrlLock = threading.Lock()
        
    def _ssdp_scan(self, st=None, ssdpTimeout=5):
        # needed for discovering the setup of upnp
        # sends a message over the network to discover upnp devices.
        # limits the results to the desired Host
        # based on some ideas on netdisco
        # wir suchen nach allen services
        ssdp_st = st or 'ssdp:all'
        ssdp_target = ('239.255.255.250', 1900)
        ssdp_request = '\r\n'.join([
            'M-SEARCH * HTTP/1.1',
            'HOST: 239.255.255.250:1900',
            'MAN: "ssdp:discover"',
            'MX: {:d}'.format(ssdpTimeout),
            'ST: {}'.format(ssdp_st),
            '', '']).encode('ascii')
        # rueckgabewerte als dict über alle services fuer alle hosts
        result = {}
        # zeiterfassung, damit das discover nicht beliebig lange läuft.    
        try:
            # timeout setzen
            socket.setdefaulttimeout(ssdpTimeout)
            # socket aufmachen
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # optionen setzen
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            # request abschicken
            sock.sendto(ssdp_request, ssdp_target)
            # schleife zum abfragen der werte
            while True:
                try:
                    # werte lesen
                    response = sock.recv(1024).decode()
                    # in einzelne zeilen zerlegen
                    response = response.split('\r\n')
                    # liste für rückgabe erstellen
                    entries = {}
                    # die erste zeile enthält nur 200 OK, daher start mit der 2. zeile
                    for line in response[1:]:
                        # leider auch leere zeilen dabei
                        if len(line) > 0:
                            item, value = line.split(':', 1)
                            # jetzt die werte in das dict eintragen
                            entries[item] = value.lstrip()
                            # wir wollen nur einen teil der services finden
                    if entries['ST'].startswith('urn:'):
                        # host adresse herausfinden (ohne port)
                        if 'LOCATION' in entries:
                            host = entries['LOCATION'].split('/')[2].split(':')[0]
                            service = entries['ST'].split(':')[3]
                            if host in result:
                                # service neu aufnehmen
                                result[host][service] = entries
                            else:
                                # host neu aufnehmen
                                result[host] = {service:entries}
                    elif entries['ST'].startswith('upnp:rootdevice'):
                        # host adresse herausfinden (ohne port)
                        if 'LOCATION' in entries:
                            host = entries['LOCATION'].split('/')[2].split(':')[0]
                            service = 'rootdevice'
                            if host in result:
                                result[host][service] = entries
                            else:
                                result[host] = {service:entries}
                    else:
                        pass
                except socket.timeout:
                    # wenn die zeit abgelaufenist, dann beenden wir die schleife
                    break
        except socket.error:
            # wenn kein socket aufgemacht werden kann, dann fehlermeldung
            logging.warning('UPNP: sspd_scan: exception socket.error')
        finally:
            # socket wieder schliessen
            if sock:
                sock.close()
        # und die rückgabe der dienste
        return result

    def _upnp_send_SOAP(self, hostName, serviceType, controlURL, actionName, actionArguments):
        # zusammenstellen aller argumente fü die  SOAP action
        argList = ''
        for arg,(val,dt) in actionArguments.iteritems():
                argList += '<%s>%s</%s>' % (arg,val,arg)
        # erstellen der SOAP anforderung
        soapBody =      '<?xml version="1.0"?>'\
                        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope" SOAP-ENV:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'\
                        '<SOAP-ENV:Body>'\
                        '<m:%s xmlns:m="%s">'\
                        '%s'\
                        '</m:%s>'\
                        '</SOAP-ENV:Body>'\
                        '</SOAP-ENV:Envelope>' % (actionName,serviceType,argList,actionName)

        # header für den request zusammenstellen
        headers =       {
                        'Host':hostName,
                        'Content-Length':len(soapBody),
                        'Content-Type':'text/xml',
                        'SOAPAction':'"%s#%s"' % (serviceType,actionName)
                        }
        uri = hostName + controlURL
        response = self.fetch_url(uri, auth=None, username=None, password=None, timeout=2, method='POST', headers=headers, body=soapBody).decode()
        return response
    
    def _parse_xml_node(self, node):
        # spezielle anpassungen für das parsen der services, damit doppelte
        # key einträge im dicts vermieden werden
        tree = {}
        for child in node.getchildren():
            childTag = child.tag                
            if child.text is not None:
                childText = child.text.strip()
            else:
                childText = ''
            childTree = self._parse_xml_node(child)
            if not childTree:
                childDict = {childTag : childText}
            else:
                if child.tag == 'service':
                    # ebene 'service' text service durch serviceType ersetzen, da sonst im dict mehrfach gleiche keys
                    # da die namen in der referenz komplex, aber als parameter immer noch enthalten, daher
                    # für device und service eine verkürzung der namen.
                    childDict = {childTree['serviceType'].split(':')[3] : childTree}
                elif child.tag == 'action':
                    # ebene 'action' text action durch action.name ersetzen, da sonst im dict mehrfach gleiche keys
                    childDict = {childTree['name'] : childTree}
                elif child.tag == 'argument':
                    # ebene 'argument' text argument durch argument.name ersetzen, da sonst im dict mehrfach gleiche keys
                    childDict = {childTree['name'] : childTree}
                else: 
                    childDict = {childTag : childTree}
            if childTag not in tree:  # First time found
                tree.update(childDict)
        return tree
    
    def _extract_devices(self, xml):
        # rückgabewert ist ein dict über alle devices aus dem xml
        devicesDict = {}
        # erst einmal aus dem xml string ein etree machen
        rootNode = et.fromstring(xml)
        # jetzt suchen wir alle knoten mit dem eintrag device
        for node in rootNode.iter('device'):
            # die machen wir zu einem dict
            device = self._parse_xml_node(node)
            # wenn sie noch nicht eingetragen sind, dann tun wir das
            if not device['deviceType'] in devicesDict:
                # allerdings machen wir die hierachie platt, d.h. wenn noch eine device list im dict hängt,
                # dann werfen wir die raus, denn die haben wir ja schon separat über die iteration über das
                # xml gemacht
                if 'deviceList' in device:
                    del device['deviceList']
                # jetzt wird sie zugewiesen
                # name device ist device type, da friendly name weniger auswertbar
                # da die namen in der referenz komplex, aber als aremeter immer noch enthalten, daher
                # für device und service eine verkürzung der namen.
                devicesDict[device['deviceType'].split(':')[3]] = device
        return devicesDict
    
    
    def upnp_discover_devices(self, hostIp = None, st = None):
        # erst einmal scannen, was es an upnp im lokalen netz gibt
        # da wir beliebig lange scannen können, die beschränkung auf 5 sekunden
        ssdpServices = self._ssdp_scan(st, ssdpTimeout=5)
        # jetzt das rückgabe dict
        upnpDevices = {}
        for host in ssdpServices:
            # jetzt noch die möglichkeit der einschränkung auf host ip's
            if host == hostIp or hostIp == None:
                # als nächste suchen wir über alle gefundenen hosteinträge
                for service in ssdpServices[host]:
                    # und es gibt mehrere einträge pro host und services nach den urls
                    response = self.fetch_url(ssdpServices[host][service]['LOCATION']).decode()
                    # um etwas übersichtlicher hinterher unterwegs im dict zu sein, nehme ich den standard heraus
                    # mehr geht leider nicht, sonst macht mit etree beim parsen des xml strings exceptions
                    # hier die devices
                    response = response.replace("xmlns='urn:schemas-upnp-org:device-1-0'", '')
                    response = response.replace('xmlns="urn:schemas-upnp-org:device-1-0"', '')
                    # für dslforum der fritzboxen
                    response = response.replace('xmlns="urn:dslforum-org:device-1-0"', '')
                    # jetzt noch den port heraussuchen
                    port = ssdpServices[host][service]['LOCATION'].split('/')[2].split(':')[1]
                    # und das dict anlegen aus der antwort
                    devicesDict = self._extract_devices(response)
                    # jetzt noch die richtuge url inkl. port dazu packen, die wird nämlich nur im ssdp scan ermittelt
                    for device in devicesDict:
                        devicesDict[device]['URL'] = 'http://' + host + ':' + port
                    # host anlegen
                    if not host in upnpDevices:
                        # erstanlage
                        upnpDevices[host] = devicesDict
                    else:
                        # jetzt müssen wir noch nachschauen, ob bei host die services schon da sind
                        # diese werden unter umständen mehrfach durch den ssdp scan angelegt und aufgerufen
                        # ich will diese aber nur einmal in der liste haben
                        for service in devicesDict:
                            if not service in upnpDevices[host]:
                                upnpDevices[host][service] = devicesDict[service]
        # jetzt suchen wir die zugehörigen actions pro service noch heraus
        for host in upnpDevices:
            for device in upnpDevices[host]:
                if 'serviceList' in upnpDevices[host][device]:
                    for service in upnpDevices[host][device]['serviceList']:
                        uri = upnpDevices[host][device]['URL'] + upnpDevices[host][device]['serviceList'][service]['SCPDURL']
                        response = self.fetch_url(uri).decode()
                        # um etwas übersichtlicher hinterher unterwegs im dict zu sein, nehme ich den standard heraus
                        # mehr geht leider nicht, sonst macht mit etree beim parsen des xml strings exceptions
                        # hier die services
                        response = response.replace("xmlns='urn:schemas-upnp-org:service-1-0'", '')
                        response = response.replace('xmlns="urn:schemas-upnp-org:service-1-0"', '')
                        # für dslforum router wie die fritzbox
                        response = response.replace('xmlns="urn:dslforum-org:service-1-0"', '')
                        rootNode = et.fromstring(response)
                        for node in rootNode.iter('action'):
                            # achtung ! hier wird nur das erste argument mit aufgenommen, das
                            action = self._parse_xml_node(node)
                            # eintragen in die Service liste
                            if not 'actionList' in upnpDevices[host][device]['serviceList'][service]:
                                upnpDevices[host][device]['serviceList'][service]['actionList'] = {}
                            if 'argumentList' in action:
                                upnpDevices[host][device]['serviceList'][service]['actionList'].update({action['name'] : action['argumentList']})
                            else:
                                upnpDevices[host][device]['serviceList'][service]['actionList'].update({action['name'] : ''})
        return upnpDevices

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    upnp=UPNP()
    upnpDevices = upnp.upnp_discover_devices(hostIp='192.168.2.1', st = 'urn:dslforum-org:device:InternetGatewayDevice:1')
    for device in upnpDevices['192.168.2.1']:
        print(device)
    pprint.pprint(upnpDevices['192.168.2.1']['LANDevice'])

