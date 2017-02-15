#!/usr/bin/env python
# encoding: utf-8
"""
consolegrid_provider.py

Created by Scott on 2013-12-26.
Copyright (c) 2013 Scott Rice. All rights reserved.
"""

import sys
import os
import urllib
import urllib2
import requests
import csv
import hashlib
from zipfile import ZipFile
import urlparse
import xml.etree.ElementTree

import grid_image_provider

from ice.logs import logger


class GamesDBProvider(grid_image_provider.GridImageProvider):
    @staticmethod
    def api_url():
        return "http://consolegrid.com/api/top_picture"

    @staticmethod
    def is_enabled():
        # TODO: Return True/False based on the current network status
        return True

    def consolegrid_top_picture_url(self, rom):
        host = self.api_url()
        quoted_name = urllib.quote(rom.name)
        return "%s?console=%s&game=%s" % (host, rom.console.shortname, quoted_name)

    def find_url_for_rom(self, rom):
        """
        Determines a suitable grid image for a given ROM by hitting
        ConsoleGrid.com
        """
        try:
            response = urllib2.urlopen(self.consolegrid_top_picture_url(rom))
            if response.getcode() == 204:
                name = rom.name
                console = rom.console.fullname
                logger.debug(
                    "ConsoleGrid has no game called `%s` for %s" % (name, console)
                )
            else:
                return response.read()
        except urllib2.URLError as error:
            # Connection was refused. ConsoleGrid may be down, or something bad
            # may have happened
            logger.debug(
                "No image was downloaded due to an error with ConsoleGrid"
            )

    def download_image(self, url):
        """
        Downloads the image at 'url' and returns the path to the image on the
        local filesystem
        """
        (path, headers) = urllib.urlretrieve(url)
        return path

    def find_hash_id_and_title(self, rom_hash):
        with open('hash.csv','r') as csvfile:
            csvreader=csv.reader(csvfile)
            for row in csvreader:
                if row[0].lower()==rom_hash.lower():
                    return row[1],row[3]
        return None,None

    def rom_hash(self, filename, method=hashlib.sha1):
        is_snes=filename.lower().endswith('.smc')
        if filename.lower().endswith('.zip'):
            zip=ZipFile(filename,'r')
            zipcontentfilename=zip.namelist()[0]
            is_snes = zipcontentfilename.lower().endswith('.smc')
            fileobj=zip.open(zipcontentfilename)
            filesize=zip.getinfo(zipcontentfilename).file_size
        else:
            fileobj=open(filename,'rb')
            filesize=os.stat(filename).st_size
        if is_snes:
            # Skip the first 512 bytes of a SNES file because that's what the CSV writer does
            if filesize%1024==512:
                fileobj.read(512)
        hasher=method()
        for chunk in iter(lambda: fileobj.read(4096), b""):
            hasher.update(chunk)
        fileobj.close()
        return hasher.hexdigest()

    def get_image_url(self, xml_url):
        e = xml.etree.ElementTree.fromstring(requests.get(xml_url).text)
        images=e.findall('Images')[0]

        def sort_key(elem):
            if elem.tag in ('fanart','screenshot'):
                key=elem.find('original')
                return -int(key.attrib['width'])*int(key.attrib['height'])
            elif elem.tag in ('boxart','banner'):
                return -int(elem.attrib['width'])*int(elem.attrib['height'])
            else:
                return 0
        for image in sorted(images,key=sort_key):
            if image.tag in ('fanart','screenshot'):
                path=image.find('original').text
            else:
                path=image.text
            return urlparse.urljoin(e.find('baseImgUrl').text,path)

    def image_for_rom(self, rom):
        if not os.path.exists('hash.csv'):
            f = urllib2.urlopen('https://raw.githubusercontent.com/sselph/scraper/master/hash.csv')
            with open('hash.csv', 'w') as hashfile:
                hashfile.write(f.read())
        gameid=None
        title=None
        for method in ('md5',):# map(lambda m: getattr(hashlib,m), hashlib.algorithms):
            hash=self.rom_hash(rom.path)
            gameid,title=self.find_hash_id_and_title(hash)
            if gameid is not None:
                break
        if gameid is None:
            logger.debug('Did not find hash for %s',rom.path)
            return None
        query=urllib.urlencode({'id':gameid})
        xml_url=urlparse.urlunparse(('http','thegamesdb.net','/api/GetArt.php','',query,''))
        image_url=self.get_image_url(xml_url)
        logger.debug('Hash-based image found: %s %s',rom.path,image_url)
        if image_url is None or image_url == "":
            return None
        return self.download_image(image_url)
