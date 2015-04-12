from PyQt5.QtWidgets import *

import fa
import modvault


GIT_ROOT = "https://github.com/FAForever/"


def filter_mod_versions(versions, filter_table):
    """
    Filters out mods that can be pulled from git repositories instead of through the obsolete updater protocol.
    :return: tuple with one list of legacy mods to keep and a dictionary of repo mods to update with the new updater
    """
    legacy = {}
    repo = {}

    if versions:
        for mod_uid in versions:
            if mod_uid in filter_table:
                repo[filter_table[mod_uid]] = versions[mod_uid]
            else:
                legacy[mod_uid] = versions[mod_uid]

    return legacy, repo


def filter_featured_mods(featured_mod, filter_table):
    """
    Filters out mods that can be pulled from git repositories instead of through the obsolete updater protocol.
    :return: tuple with a strings and a dict, either a legacy mod name or a non-legacy mod dict (name:repo) pairs
    """

    if featured_mod in filter_table:
        return None, {featured_mod:filter_table[featured_mod]}

    return featured_mod, None


import logging
logger = logging.getLogger(__name__)

def checkMods(mods):  #mods is a dictionary of uid-name pairs
    """
    Assures that the specified mods are available in FA, or returns False.
    Also sets the correct active mods in the ingame mod manager.
    """
    logger.info("Updating FA for mods %s" % ", ".join(mods))
    to_download = []
    inst = modvault.getInstalledMods()
    uids = [mod.uid for mod in inst]
    for uid in mods:
        if uid not in uids:
            to_download.append(uid)

    for uid in to_download:
        result = QMessageBox.question(None, "Download Mod",
                                            "Seems that you don't have this mod. Do you want to download it?<br/><b>" +
                                            mods[uid] + "</b>", QMessageBox.Yes, QMessageBox.No)
        if result == QMessageBox.Yes:
            # Spawn an update for the required mod
            updater = fa.updater.Updater(uid, sim=True)
            result = updater.run()
            updater = None  #Our work here is done
            if (result != fa.updater.Updater.RESULT_SUCCESS):
                return False
        else:
            return False

    actual_mods = []
    inst = modvault.getInstalledMods()
    uids = {}
    for mod in inst:
        uids[mod.uid] = mod
    for uid in mods:
        if uid not in uids:
            QMessageBox.warning(None, "Mod not Found",
                                      "%s was apparently not installed correctly. Please check this." % mods[uid])
            return
        actual_mods.append(uids[uid])
    if not modvault.setActiveMods(actual_mods):
        logger.warn("Couldn't set the active mods in the game.prefs file")
        return False

    return True
