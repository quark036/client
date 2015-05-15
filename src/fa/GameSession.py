__author__ = 'vytautas'

import os
from os import path
import logging

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtNetwork import *

import util
from client import instance as client

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from .GameConnection import GameConnection

class SessionSetupFailed(Exception):
    pass

class GameSession(QObject):

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super(GameSession, self).__init__(parent)

        self._proc = QProcess()

        self._proc.started.connect(self._onStarted)
        self._proc.error.connect(self._onError)
        self._proc.finished.connect(self._onFinished)

        self._proc.readyReadStandardOutput.connect(self._onReadyReadStandardOutput)
        self._proc.readyReadStandardError.connect(self._onReadyReadStandardError)

        self.gamePort = client.gamePort

        self._GameState = None
        self._arguments = dict()

        # Session parameter defaults
        self._joinGameAddr = None
        self.gameMods = []
        self.mapName = None #'scmp_009'
        self.gameTitle = "No title."
        self.playerName = "Player"
        self.playerUID = 0

        self._faf_conn = None

        self._game_listener = QTcpServer(self)
        assert self._game_listener.listen(QHostAddress.LocalHost)
        self._game_listener.newConnection.connect(self._onNewGameConnection)

        self._replay_listener = None
        self._replay_stream = None
        self._replay_endpoints = []

        self.addArg('nobugreport')
        self.addArg('gpgnet', '127.0.0.1:%d' % self._game_listener.serverPort())

    # Session command-line arguments
    def addArg(self, key, *args):

        assert key and isinstance(key, str)

        self._arguments[key] = args

    # Session parameters
    def setJoinGame(self, game_id, joinGameAddress):
        self._joinGameId = game_id
        self._joinGameAddr = joinGameAddress

    def setMods(self, gameMods):
        self.gameMods = list(gameMods)

    def setMap(self, mapName):
        self.mapName = mapName

    def setTitle(self, gameTitle):
        self.gameTitle = gameTitle

    def setLocalPlayer(self, playerName, playerUID=0):
        self.playerName = str(playerName)
        self.playerUID = playerUID

    def saveReplay(self, endpoint_dev:QIODevice):
        """
        Save session replay to device: Can be anything.

        Can be called multiple times to declare multiple endpoints.
        """

        if not self._replay_listener:
            self._replay_listener = QTcpServer(self)
            assert self._replay_listener.listen(QHostAddress.LocalHost)
            self._replay_listener.newConnection.connect(self._onNewReplayStream)
            self.addArg('savereplay', 'gpgnet://127.0.0.1:%d' % self._replay_listener.serverPort())

        assert isinstance(endpoint_dev, QIODevice)
        if isinstance(endpoint_dev, QAbstractSocket):
            endpoint_dev.setSocketOption(QAbstractSocket.LowDelayOption, 1)

        self._replay_endpoints.append(endpoint_dev)

    # FAF Connection
    def setFAFConnection(self, faf_conn):
        self._faf_conn = faf_conn
        faf_conn.faf_games.connect(self._onFAFMessage)

    def _sendFAF(self, command_id, args):
        if self._faf_conn:
            logger.debug("FAF S: %s : %s", command_id, args)
            self._faf_conn.sendGames(command_id, args)

    def _onFAFMessage(self, command_id, args):
        logger.debug("FAF R: %s : %s", command_id, args)

        if command_id == 'open_resp' and args['success'] == False:
            raise RuntimeError("Failed to open game on server. Should not happen here.")
        elif command_id in ['ConnectToPeer', 'JoinGame']:
            self._conn.send(command_id, *args)

    # Start the session (FA)
    def start(self, program=None):

        program = program or path.join(util.BIN_DIR, "ForgedAlliance.exe")

        logger.info("Launching FA: %s", program)
        arguments = []

        for key, value in list(self._arguments.items()):
            arguments.append('/'+str(key))
            arguments.extend([ (str(x) if isinstance(x, int) else '%s' % str(x))
                                       for x in value])

        logger.info("Launching FA: %s", arguments)

        self._proc.setWorkingDirectory(util.BIN_DIR)

        if os.name != 'nt':
            # Naive Wine cross-platform
            arguments.insert(0, program)
            program = 'wine'

            # Try to accomodate bumblebee users on linux.
            # FIXME: Should use shutil.which on python 3.3
            # if os.stat('/usr/bin/optirun'):
            #     arguments.insert(0, program)
            #     program = 'optirun'
        self._proc.start(program, arguments)

    # Stop/Kill session
    def stop(self):
        self._proc.terminate()

    def kill(self):
        self._proc.kill()

    # FA Running?
    def isRunnning(self):
        return self._proc.state() == QProcess.Running

    # GameState (str)
    def gameState(self):
        return self._GameState

    # Replay Stream
    def _onNewReplayStream(self):
        self._replay_stream = self._replay_listener.nextPendingConnection()
        self._replay_stream.readyRead.connect(self._replayRead)
        self._replay_stream.disconnected.connect(self._replayDone)
        logger.info("ReplayStream: connected.")

        del self._replay_listener

        self._replay_stream_first = False # Has the first packet been read

    def _replayRead(self):
        dev = self._replay_stream
        data = dev.readAll()

        if not self._replay_stream_first:
            # Strip Gpgnet 'POST' prefix
            assert data[0] == 'P'
            data.remove(0, data.indexOf(b'\x00')+1)

            for endpoint in self._replay_endpoints:
                if isinstance(endpoint, QAbstractSocket):
                    endpoint.write('P/%d/%s.fafreplay' % (self.playerUID, self.playerName))

            self._replay_stream_first = True

        for endpoint in self._replay_endpoints:
            endpoint.write(data)
            if isinstance(endpoint, QAbstractSocket):
                endpoint.flush()

    def _replayDone(self):
        self._replayRead()

        for endpoint in self._replay_endpoints:
            endpoint.close()

        logger.info("ReplayStream: disconnected/finished.")

    # Game Connection
    def _onNewGameConnection(self):
        self._conn = GameConnection(self._game_listener.nextPendingConnection())
        self._conn.messageReceived.connect(self._onGameConnectionMessage)
        self._conn.closed.connect(self._onGameConnectionClosed)
        logger.info("GC: connected.")

        del self._game_listener

    def _onGameConnectionMessage(self, command, args):
        if command == "GameState":
            if args[0] == 'Idle':
                                       # autolobby, port, nickname, uid, hasSupcom
                self._conn.send("CreateLobby", 0, self.gamePort,
                                                  self.playerName, self.playerUID, 1)
                return # Only initialize the game
            elif args[0] == 'Lobby':
                if self._joinGameAddr: # We're joining
                    self._sendFAF('join', [self._joinGameId, self.gamePort])
                    #self._conn.send("JoinGame")

                else: # We're hosting
                    if self._faf_conn: # Tell FAF
                        self._sendFAF("open", { 'port': self.gamePort,
                                                'title': self.gameTitle})

                    if self.mapName:
                        self._conn.send("HostGame", self.mapName)
                    else:
                        self._conn.send("HostGame")

                #self._conn.send("SendNatPacket", "127.0.0.1:8002", "foot")
                #self._conn.send("HasSupcom", 0)
                #self._conn.send("Test", "Banana", "Foot", "Kiwi")
                #self._conn.send("SetGameOption", "OmniCheat", "on")
            self._GameState = args[0]

        if command in ["GameState", "GameOption", "GameMods", "PlayerOption", "Chat"]:
            self._sendFAF(command, args)

    def _onGameConnectionClosed(self):
        logger.info("GC: disconnected.")

    # FA Process events
    def _onStarted(self):
        logger.info("FA started.")

    def _onError(self, error):
        logger.error("FA failed to start: %s", self._proc.errorString())

    def _onFinished(self, exitCode, exitStatus):
        logger.info("FA Finished: %d, %s", exitCode, exitStatus)
        self._sendFAF('close', {})
        self.finished.emit()

    def _onReadyReadStandardOutput(self):
        while self._proc.canReadLine():
            logger.info("FA Out: %s" % self._proc.readLine())

    def _onReadyReadStandardError(self):
        while self._proc.canReadLine():
            logger.info("FA Err: %s" % self._proc.readLine())

    # Game Session Starters
    @staticmethod
    def Replay(version='faf_v1'):
        versions = { 'faf_v1': GameSession._Replay_faf_v1}

        if version in versions:
            return versions[version]()
        else:
            QMessageBox.error("Game Launch", 'Unknown replay version: "%s"' % version)
            raise SessionSetupFailed('Unknown replay version: "%s"' % version)



    @staticmethod
    def Matchmaker():
        session = GameSession()

        session.addArg("log", util.LOG_FILE_GAME)

        return session

    @staticmethod
    def CustomGame(joinGameURL = None):
        session = GameSession()

        session.setJoinGame(joinGameURL)

        session.addArg("log", util.LOG_FILE_GAME)

        return session

    @staticmethod
    def _Replay_faf_v1():
        session = GameSession()

        session.addArg("log", util.LOG_FILE_REPLAY)

        return session
