#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'videns'
import inspect
import pkgutil
import json
import os
try:
    import urllib.request as urllib2
except ImportError:
    import urllib2
import scanModules


VULNERS_LINKS = {'pkgChecker':'https://vulners.com/api/v3/audit/audit/',
                 'bulletin':'https://vulners.com/api/v3/search/id/'}

VULNERS_ASCII = r"""
             _
__   ___   _| |_ __   ___ _ __ ___
\ \ / / | | | | '_ \ / _ \ '__/ __|
 \ V /| |_| | | | | |  __/ |  \__ \
  \_/  \__,_|_|_| |_|\___|_|  |___/

"""


class scannerEngine():
    def __init__(self):
        self.osInstanceClasses = self.getInstanceClasses()

    def getInstanceClasses(self):
        self.detectors = None
        members = set()
        for modPath, modName, isPkg in pkgutil.iter_modules(scanModules.__path__):
            #find all classed inherited from scanner.osDetect.ScannerInterface in all files
            members = members.union(inspect.getmembers(__import__('%s.%s' % ('scanModules',modName), fromlist=['scanModules']),
                                         lambda member:inspect.isclass(member)
                                                       and issubclass(member, scanModules.osDetect.ScannerInterface)
                                                       and member.__module__ == '%s.%s' % ('scanModules',modName)
                                                       and member != scanModules.osDetect.ScannerInterface))
        return members

    def getInstance(self,sshPrefix):
        inited = [instance[1](sshPrefix) for instance in self.osInstanceClasses]
        if not inited:
            raise Exception("No OS Detection classes found")
        osInstance = max(inited, key=lambda x:x.osDetectionWeight)
        if osInstance.osDetectionWeight:
            return osInstance

    def sendVulnRequest(self, url, payload):
        req = urllib2.Request(url)
        req.add_header('Content-Type', 'application/json')
        response = urllib2.urlopen(req, json.dumps(payload).encode('utf-8'))
        responseData = response.read()
        if isinstance(responseData, bytes):
            responseData = responseData.decode('utf8')
        responseData = json.loads(responseData)
        return responseData

    def auditSystem(self, sshPrefix, systemInfo=None):
        audit_system_results = {}
        instance = self.getInstance(sshPrefix)
        installedPackages = instance.getPkg()
        print("="*42)
        if systemInfo:
            print("Host info - %s" % systemInfo)
        audit_system_results['os_version'] = ("OS Name - %s, OS Version - %s" % (instance.osFamily, instance.osVersion))
        print("OS Name - %s, OS Version - %s" % (instance.osFamily, instance.osVersion))
        audit_system_results['total_packages'] = len(installedPackages)
        audit_system_results['data'] = []
        print("Total found packages: %s" % len(installedPackages))
        if not installedPackages:
            return instance
        # Get vulnerability information
        payload = {'os':instance.osFamily,
                   'version':instance.osVersion,
                   'package':installedPackages}
        url = VULNERS_LINKS.get('pkgChecker')
        response = self.sendVulnRequest(url, payload)
        resultCode = response.get("result")
        if resultCode != "OK":
            print("Error - %s" % response.get('data').get('error'))
        else:
            vulnsFound = response.get('data').get('vulnerabilities')
            if not vulnsFound:
                print("No vulnerabilities found")
            else:
                payload = {'id':vulnsFound}
                allVulnsInfo = self.sendVulnRequest(VULNERS_LINKS['bulletin'], payload)
                vulnInfoFound = allVulnsInfo['result'] == 'OK'
                print("Vulnerable packages:")
                for package in response['data']['packages']:
                    print(" "*4 + package)
                    packageVulns = []
                    for vulns in response['data']['packages'][package]:
                        if vulnInfoFound:
                            vulnInfo = "{id} - '{title}', cvss.score - {score}".format(id=vulns,
                                                                                       title=allVulnsInfo['data']['documents'][vulns]['title'],
                                                                                       score=allVulnsInfo['data']['documents'][vulns]['cvss']['score'])
                            packageVulns.append((vulnInfo,allVulnsInfo['data']['documents'][vulns]['cvss']['score']))
                            temp = {}
                            temp['id'] = vulns
                            temp['title'] = allVulnsInfo['data']['documents'][vulns]['title']
                            temp['cvss_score'] = allVulnsInfo['data']['documents'][vulns]['cvss']['score']
                            audit_system_results['data'].append(temp)
                        else:
                            packageVulns.append((vulns,0))
                    packageVulns = sorted(packageVulns, key=lambda x:x[1])
                    packageVulns = [" "*8 + x[0] for x in packageVulns]
                    print("\n".join(packageVulns))
        return audit_system_results
        # return instance

    def scanDocker(self, dockerID, dockerImage):
        sshPrefix = "docker exec %s" % dockerID
        results = self.auditSystem(sshPrefix, "docker container \"%s\"" % dockerImage)
        return results

    def scan(self, dockerID = False, dockerImage = False, checkDocker = False):
        container_results = []
        #scan host machine
        # hostInstance = self.auditSystem(sshPrefix=None,systemInfo="Host machine")
        #scan dockers
        hostInstance = self.getInstance(sshPrefix=None)
        if checkDocker:
            if dockerID and dockerImage:
                container_results.append(self.scanDocker(dockerID, dockerImage))
            else:
                containers = hostInstance.sshCommand("docker ps")
                if containers:
                    containers = containers.splitlines()[1:]
                    dockers = [(line.split()[0], line.split()[1]) for line in containers]
                    for (dockerID, dockerImage) in dockers:
                        container_results.append(self.scanDocker(dockerID, dockerImage))

        return container_results

if __name__ == "__main__":
    # print('\n'.join(VULNERS_ASCII.splitlines()))
    scannerInstance = scannerEngine()
    results = scannerInstance.scan(checkDocker=True)
