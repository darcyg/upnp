#!/usr/bin/env python3
# vim: set encoding=utf-8 tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#
# Copyright (C) 2015 Michael Würtenberger
#
# UPNP Services / library for Plugins for sh.py
#
# v 0.1
#
# is not a real upnp client implementation, but installs the necessary service to get
# an standard environment to work, tested on a simple bases !

import select
import socket
import logging
from lib.www import Client
import xml.etree.ElementTree as et
from datetime import datetime
import pprint

logger = logging.getLogger('UPNP')

class UPNP():
    
    def _ssdp_scan(self, st=None, ssdpTimeout=5):
        # needed for discovering the setup of upnp
        # sends a message over the network to discover upnp devices.
        # limits the results to the desired Host
        # based on some ideas on netdisco
        # wir suchen nach allen services
        ssdp_st = st or "ssdp:all"
        ssdp_target = ("239.255.255.250", 1900)
        ssdp_request = "\r\n".join([
            'M-SEARCH * HTTP/1.1',
            'HOST: 239.255.255.250:1900',
            'MAN: "ssdp:discover"',
            'MX: {:d}'.format(ssdpTimeout),
            'ST: {}'.format(ssdp_st),
            '', '']).encode('ascii')
        # rueckgabewerte als dict über alle services fuer alle hosts
        result = {}
        # zeiterfassung, damit das discover nicht beliebig lange läuft.    
        calc_now = datetime.now
        start = calc_now()
        ssdpRunning = True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(ssdp_request, ssdp_target)
            sock.setblocking(0)
            while ssdpRunning:
                # abfrage der abgelaufenen zeit
                time_diff = calc_now() - start
                seconds_left = ssdpTimeout - time_diff.seconds
                if seconds_left <= 0:
                    # wenn die zeit abgelaufen ist, dann schleife stoppen
                    ssdpRunning = False
                ready = select.select([sock], [], [], seconds_left)[0]
                if ready:
                    # daten lesen
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
    #                        print(entries['ST']) 
        except socket.error:
            logging.warning('UPNP: sspd_scan: exception socket.error')
        finally:
            sock.close()
        return result
    
    def _parse_xml_node(self, node):
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
                childDict = {childTag : childTree}
            if childTag not in tree:  # First time found
                tree.update(childDict)
        return tree
    
    def _extract_devices(self, xml):
        # rückgabewert ist ein dict über alle devices aus dem xml
        devicesDict = {}
        # erst einmal aus dem xml string ein etree machen
        EL = et.fromstring(xml)
        # jetzt suchen wir alle knoten mit dem eintrag device
        for node in EL.iter('device'):
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
                devicesDict[device['deviceType']] = device
        return devicesDict
    
    def upnp_find_sevices(self):
        # erst einmal scannen, was es an upnp im lokalen netz gibt
        # da wir beliebig lange scannen können, die beschränkung auf 5 sekunden
        ssdpServices = self._ssdp_scan(ssdpTimeout=5)
        # jetzt das rückgabe dict
        upnpDevices = {}
        for host in ssdpServices:
            # als nächste suchen wir über alle gefundenen hosteinträge
            for service in ssdpServices[host]:
                # und es gibt mehrere einträge pro host und services nach den urls
                response = Client.fetch_url('', ssdpServices[host][service]['LOCATION']).decode()
                # um etwas übersichtlicher hinterher unterwegs im dict zu sein, nehme ich den standard heraus
                # mehr geht leider nicht, sonst macht mit etree beim parsen des xml strings exceptions
                response = response.replace("xmlns='urn:schemas-upnp-org:device-1-0'", '')
                response = response.replace('xmlns="urn:schemas-upnp-org:device-1-0"', '')
                # jetzt noch den port heraussuchen
                port = ssdpServices[host][service]['LOCATION'].split('/')[2].split(':')[1]
                # und das dict anlegen aus der antwort
                devicesDict = self._extract_devices(response)
                # jetzt noch die richtuge url inkl. port dazu packen, die wird nämlich nur im ssdp scan ermittelt
                for service in devicesDict:
                    devicesDict[service]['URL'] = host + ':' + port
                # wenn noch kein host angelegt, dann anlegen
                if not host in upnpDevices:
                    # erstanlage
                    upnpDevices[host] = devicesDict
                else:
                    # jetzt müssen wir noch nachschauen, ob bei host die services schon da sind
                    # diese werden unter umständen mehrfach durch den ssdp scan angelegt und aufgerufen
                    # ich will diese aber nur einmal in der liste haben
                    for serviceType in devicesDict:
                        if not serviceType in upnpDevices[host]:
                            upnpDevices[host][serviceType] = devicesDict[serviceType]
        return upnpDevices

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    upnp=UPNP()
    upnpDevices = upnp.upnp_find_sevices()
    for host in upnpDevices:
        for service in upnpDevices[host]:
            print(upnpDevices[host][service]['URL'],'-->',upnpDevices[host][service]['friendlyName'])
#            pprint.pprint(upnpDevices[host][service])

