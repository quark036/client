"""
Shall handle all resources (mods/maps/engine) for FAF
"""

import os, shutil
from os.path import join as pjoin
from collections import ChainMap
from PyQt5.QtCore import *

from git.version import Version

import modvault.utils
MOD_FOLDER = modvault.utils.MODFOLDER

if not os.path.exists(MOD_FOLDER):
    os.makedirs(MOD_FOLDER)

from .resource import Engine, Mod, Map
from git.repository import Repository

from contextlib import contextmanager

class Task(QObject):

    state = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()

    def __init__(self, name):
        QObject.__init__(self)
        self._name = name
        self._state = 'none'
        self._max = None
        self._progress = (0, 0)
        self._finished = False

    def get_name(self):
        return self._name

    def get_state(self):
        'Ret: "Current State"'
        return self._state

    def get_progress(self):
        "Ret: (cur, max)"
        return self._progress

    def set_state(self, state):
        self._state = state
        self.state.emit(state)

    def set_max(self, max):
        self._max = max

    def set_progress(self, cur, max=None):
        self._progress = (cur, max or self._max)
        self.progress.emit(cur, max)

    def set_finished(self,  final_state=None):
        if final_state:
            self.set_state(final_state)
        self.set_progress(100, 100)
        self._finished = True
        self.finished.emit()

    def is_finished(self):
        return self._finished

class FAResources(QObject):

    task_started = pyqtSignal(Task)

    def __init__(self, resource_folder, parent=None):
        super(FAResources, self).__init__(parent)

        self._thread = QThread()
        self._thread.start()
        self.moveToThread(self._thread)

        self._engine = {}
        self._mods   = {}
        self._maps   = {}

        self._resources = ChainMap(self._engine, self._mods, self._maps)

        self._engine_folder = pjoin(resource_folder, 'Engine')
        self._mod_folder = pjoin(resource_folder, 'Mods')
        self._map_folder = pjoin(resource_folder, 'Maps')

        for folder in [self._engine_folder, self._mod_folder, self._map_folder]:
            if not os.path.exists(folder):
                os.makedirs(folder)

        self._tasks = set()

    def tasks(self):
        return self._tasks

    @contextmanager
    def _new_task(self, name):
        t = Task(name)
        self._tasks.add(t)
        try:
            yield t
        finally:
            if not t.is_finished():
                t.set_finished()
            self._tasks.remove(t)

    # ==== Synchronize, List available resources ====
    @pyqtSlot()
    def _sync(self):
        "Synchronize with what we have on the filesystem. Filesystem -> this"
        self._sync_engine()
        self._sync_maps()
        self._sync_mods()

    @pyqtSlot()
    def _sync_engine(self):
        self._engine.clear()
        for engine_folder in os.listdir(self._engine_folder):
            self._engine[engine_folder] = Engine(pjoin(self._engine_folder, engine_folder))


    @pyqtSlot()
    def _sync_mods(self):
        with self._new_task('Synchronizing Mods') as task:
            self._mods.clear()
            mod_folders = os.listdir(self._mod_folder)
            length = len(mod_folders)
            for i in range(length):
                mod_folder = mod_folders[i]
                task.set_state('Loading "%s"' % mod_folder)
                self._mods[mod_folder] = Mod(pjoin(self._mod_folder, mod_folder))
                task.set_progress(i+1, length)

    @pyqtSlot()
    def _sync_maps(self):
        self._maps.clear()
        for map_folder in os.listdir(self._map_folder):
            self._maps[map_folder] = Map(pjoin(self._map_folder, map_folder))

    def Synchronize(self, type=None):
        slot = '_sync'
        if type == 'engine':
            slot = '_sync_engine'
        elif type == 'mod':
            slot = '_sync_mods'
        elif type == 'map':
            slot = '_sync_maps'

        QMetaObject.invokeMethod(self, slot)

    def Available(self):
        return self._resources.copy()

    def AvailableEngine(self):
        return self._engine.copy()

    def AvailableMods(self):
        return self._mods.copy()

    def AvailableMaps(self):
        return self._maps.copy()

    def GetRes(self, type, name):
        if type == 'engine':
            return self._engine.get(name)
        elif type == 'mod':
            return self._mods.get(name)
        elif type == 'map':
            return self._maps.get(name)

    def IsAvailable(self, type, name):
        return self.GetRes(type, name) and True

    # ==== Update and Download ====
    def _get_resource(self, type, name):
        return self._resources.get(name)

    def _get_folder(self, type):
        if type == 'engine':
            return self._engine_folder
        elif type == 'mod':
            return self._mod_folder
        elif type == 'map':
            return self._map_folder

    @pyqtSlot(str, object)
    def _update_resource(self, type, version: Version):
        "Checks, Updates or Downloads a resource."

        resource = self._get_resource(type, version.repo_name)

        if not resource:
            # Download
            folder = pjoin(self._get_folder(type), version.repo_name)
            repo = Repository(folder, version.url)
            repo.checkout_version(version)

            if type == 'engine':
                resource = Engine(folder)
            elif type == 'mod':
                resource = Mod(folder)
            elif type == 'map':
                resource = Map(folder)
        else:
            repo = resource.GetRepo()
            repo.fetch_version(version)
            repo.checkout_version(version)

        if type == 'engine':
            self._engine[version.repo_name] = resource
        elif type == 'mod':
            self._mods[version.repo_name] = resource
        elif type == 'map':
            self._maps[version.repo_name] = resource

        return resource

    def _update(self, engine=True, mods=True, maps=True):
        types = dict(engine=engine, mods=mods, maps=maps)

        for res in self._resources.values():
            if types.get(res.type):
                repo = res.GetRepo()
                repo.fetch()
                repo.checkout()

    def Update(self, engine=True, mods=True, maps=True):
        "Update resources"
        QMetaObject.invokeMethod(self, '_update',
                                 Q_ARG(bool, engine), Q_ARG(bool, mods), Q_ARG(bool, maps))

    def AddResource(self, version: Version):
        "Add or Update to version"
        # FIXME: Special-cased FAF
        if version.type == 'main_mod':
            version.type = 'mod'

        if version.type not in {'engine', 'mod', 'map'}:
            raise ValueError("Unknown resource type: %s", version.type)

        QMetaObject.invokeMethod(self, '_update_resource', Q_ARG(str, version.type), Q_ARG(object, version))
