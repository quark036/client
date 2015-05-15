__author__ = 'Thygrrr'

import os
import re
from urllib.parse import urlparse
import pygit2

import logging
logger = logging.getLogger(__name__)

from PyQt5.QtCore import *

class Repository(QObject):

    progress_state = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    progress_maximum  = pyqtSignal(int)
    progress_complete = pyqtSignal()

    def __init__(self, path, url=None, parent=None):
        QObject.__init__(self, parent)

        assert path

        self._path = path
        self.url = url

        logger.debug("Opening repository at " + self.path)
        if not os.path.exists(self.path):
            if not self.url:
                raise RuntimeError('Cannot create git.Repository with an empty path and no url.')

            logger.debug("Cloning %s into %s", self.url, self.path)
            self.repo = pygit2.init_repository(self.path)
            self.fetch_url(url)
        else:
            if not os.path.exists(os.path.join(self.path, ".git")):
                raise pygit2.GitError(self.path + " doesn't seem to be a git repo. libgit2 might crash.")
            self.repo = pygit2.Repository(self.path)

    def __del__(self):
        self.close()

    def close(self):
        del self.repo

    @property
    def path(self):
        return self._path

    @property
    def tags(self):
        regex = re.compile('^refs/tags/(.*)')
        return [regex.match(r).group(1) for r in self.repo.listall_references() if regex.match(r)]

    @property
    def remote_branches(self):
        return self.repo.listall_branches(pygit2.GIT_BRANCH_REMOTE)

    @property
    def local_branches(self):
        return self.repo.listall_branches(pygit2.GIT_BRANCH_LOCAL)

    @property
    def remote_names(self):
        return [remote.name for remote in self.repo.remotes]

    @property
    def remote_urls(self):
        return [remote.url for remote in self.repo.remotes]

    @property
    def current_head(self):
        return self.repo.head.target

    def _sideband(self, operation):
        self.progress_state.emit(operation)

    def _transfer(self, transfer_progress):
        self.progress_max.emit(transfer_progress.total_objects)
        self.progress_value.emit(transfer_progress.received_objects)

    def has_hex(self, hex):
        try:
            return hex in self.repo
        except (KeyError, ValueError):
            return False

    def has_version(self, version):
        try:
            ref_object = self.repo.get(self.repo.lookup_reference("refs/tags/"+version.ref).target)
            if isinstance(ref_object, pygit2.Tag):
                if ref_object.target:
                    return self.has_hex(version.hash) and ref_object.target.hex == version.hash
        except KeyError:
            pass
        return self.has_hex(version.hash)

    def _build_remote(self, url_str):
        url = urlparse(url_str)
        if url.hostname.endswith('faforever.com'):
            remote_name = 'faf'
        else:
            remote_name = '_'.join(reversed(url.hostname.split('.'))) \
                        + '_'.join(url.path.split('/')[:2])

        logger.debug("Adding remote %s -> %s in %s", remote_name, url_str, self.path)
        return self.repo.create_remote(remote_name, url_str)

    def fetch_remote(self, remote: pygit2.Remote):
        logger.debug("Fetching '" + remote.name + "' from " + remote.url)
        remote.sideband_progress = self._sideband
        remote.transfer_progress = self._transfer
        remote.fetch()

    def fetch(self):
        for remote in self.repo.remotes:
            self.fetch_remote(remote)

        # It's not entirely clear why this needs to happen, but libgit2 expects the head to point somewhere after fetch
        if self.repo.listall_references():
            self.repo.set_head(self.repo.listall_references()[0])

        self.progress_complete.emit()

    def fetch_url(self, url_str):
        remotes = {r.url: r for r in self.repo.remotes}

        remote = remotes.get(url_str)
        if not remote:
            remote = self._build_remote(url_str)

        remote.fetch()

        if self.repo.listall_references():
            self.repo.set_head(self.repo.listall_references()[0])

        self.progress_complete.emit()

    def fetch_version(self, version):
        self.fetch_url(version.url)

    def checkout(self, target="faf/master"):
        logger.debug("Checking out " + target + " in " + self.path)
        if target in self.remote_branches:
            self.repo.checkout(self.repo.lookup_branch(target, pygit2.GIT_BRANCH_REMOTE), strategy=pygit2.GIT_CHECKOUT_FORCE)
        elif target in self.local_branches:
            self.repo.checkout(self.repo.lookup_branch(target, pygit2.GIT_BRANCH_LOCAL), strategy=pygit2.GIT_CHECKOUT_FORCE)
        elif target in self.tags:
            self.repo.checkout(self.repo.lookup_reference("refs/tags/" + target), strategy=pygit2.GIT_CHECKOUT_FORCE)
        else:
            try:
                ob = self.repo[target]
                self.repo.checkout_tree(ob, strategy=pygit2.GIT_CHECKOUT_FORCE)
            except KeyError:
                raise pygit2.GitError('No such oid: %s' % target)

    def checkout_version(self, version):
        if version.hash:
            return self.checkout(version.hash)
        elif version.ref:
            return self.checkout(version.ref)
        else:
            raise KeyError("Version doesn't have a hash or ref")
