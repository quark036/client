"""
FA Resources: Engine, Mods, Maps
"""

import os
from os.path import abspath, join as pjoin, exists, basename

import zipfile

from util import loadLua
from git.repository import Repository

class FAResource:
    def __init__(self, type, folder_or_zip):
        self.type = type

        self.folder = abspath(folder_or_zip)

        self._repo = None

    def IsZip(self):
        return not os.path.isdir(self.folder)

    def IsRepo(self):
        return self.IsZip() or exists(pjoin(self.folder, '.git'))

    def GetRepo(self):
        if not self._repo:
            self._repo = Repository(self.folder)
        return self._repo

    def GetRepoVersion(self):
        if self.IsRepo():
            return self.GetRepo()

class Engine(FAResource):
    def __init__(self, folder_or_zip):
        super(Engine, self).__init__('engine', folder_or_zip)

    def __repr__(self):
        folder = '/'.join(self.folder.split('/')[-1:])
        return 'Engine( %s)' % (folder)


class Mod(FAResource):
    def __init__(self, folder_or_zip):
        super(Mod, self).__init__('mod', folder_or_zip)

        if not os.path.isdir(folder_or_zip):
            zip = zipfile.ZipFile(folder_or_zip)
            assert zip.testzip() == None

            lua = loadLua(zip.read('mod_info.lua'))
        else:
            try:
                lua = loadLua(open(pjoin(folder_or_zip, 'mod_info.lua'), 'rb').read())
            except FileNotFoundError:
                # FIXME: Assuming we are in a main_mod
                self.name = self.uid = basename(folder_or_zip)
                self.main_mod = True
                self.version = self.author = self.description = self.ui_only = None
                return
        self.name = lua.eval('name')
        self.uid  = lua.eval('uid')
        self.version = lua.eval('version')
        self.author = lua.eval('author')
        self.description = lua.eval('description')
        self.ui_only = lua.eval('ui_only')
        self.main_mod = lua.eval('main_mod')

    def __repr__(self):
        folder = '/'.join(self.folder.split('/')[-1:])
        return 'Mod( %s, %s, %s)' % (self.name, self.uid, folder)



class Map(FAResource):
    def __init__(self, folder_or_zip):
        super(Map, self).__init__('map', folder_or_zip)

    def __repr__(self):
        folder = '/'.join(self.folder.split('/')[-1:])
        return 'Map( %s)' % (folder)
