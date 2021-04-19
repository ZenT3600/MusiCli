import os
import curses
import sys
import time
import random
import kthread
import string

from pathlib import Path

from tinytag import TinyTag
from mutagen.id3 import ID3, TALB, TIT2, TPE1
from mutagen.mp3 import MP3
from pygame import mixer
from typing import List, Dict
from pyfiglet import Figlet

import Parser


pathsep = os.path.sep
supportedExtensions = ["mp3", ]


class Song:
    def __init__(self, path):
        self.path = path
        self.__loadMetadata()

    def __str__(self):
        return str(self.title)

    def __loadMetadata(self):
        try:
            self.__length = MP3(self.path).info.length
            self.__id3 = ID3(self.path)
            self.__title = str(self.__id3["TIT2"])
            self.__artist = str(self.__id3["TPE1"])
            self.__album = str(self.__id3["TALB"])
        except:
            self.__length = self.__title = self.__artist = self.__album = "[ Unknown ]"

        self.__tinytag = TinyTag.get(self.path)
        self.__track = self.__tinytag.track
        self.__track_total = self.__tinytag.track_total

    @property
    def length(self):
        return self.__length

    @property
    def track(self):
        return self.__track

    @property
    def track_total(self):
        return self.__track_total

    @property
    def title(self):
        return self.__title

    @title.setter
    def title(self, value):
        self.__id3["TIT2"] = TIT2(encoding=3, text=value)
        self.__id3.save(self.path)
        self.__loadMetadata()

    @property
    def artist(self):
        return self.__artist

    @artist.setter
    def artist(self, value):
        self.__id3["TPE1"] = TPE1(encoding=3, text=value)
        self.__id3.save(self.path)
        self.__loadMetadata()

    @property
    def album(self):
        return self.__album

    @album.setter
    def album(self, value):
        self.__id3["TALB"] = TALB(encoding=3, text=value)
        self.__id3.save(self.path)
        self.__loadMetadata()


class Album:
    def __init__(self, name, *args):
        self.__name = name
        self.__songs = []
        for song in args:
            self.__songs.append(song)

    def __len__(self):
        return len(self.allSongs)

    def __getitem__(self, index):
        return self.allSongs[index]

    def index(self, value):
        return self.allSongs.index(value)

    @property
    def allSongs(self):
        return self.__songs

    @property
    def name(self):
        return self.__name

    def append(self, song):
        self.__songs.append(song)

    def pop(self, index):
        self.__songs.pop(index)


class Queue:
    def __init__(self, *args):
        self.__index = 0
        self.__songs = []
        for song in args:
            if song != "..":
                self.__songs.append(Song(song) if isinstance(song, str) else song)

    def __len__(self):
        return len(self.allSongs)

    def __getitem__(self, index):
        return self.allSongs[index]

    @property
    def allSongs(self):
        return self.__songs

    @property
    def index(self):
        return self.__index

    @index.setter
    def index(self, i):
        self.__index = i

    @property
    def next(self):
        return self.__songs[self.index + 1]

    def append(self, song):
        self.__songs.append(song)

    def pop(self, index):
        self.__songs.pop(index)


class Player:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        #self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.resize_term(*self.stdscr.getmaxyx())
        curses.start_color()
        curses.init_color(11, 23, 204, 343)
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, 11, curses.COLOR_BLACK)
        self.stdscr.keypad(True)
        mixer.init()

        self.playingSong = None
        self.selectedEntry = None
        self.selectedAlbumName = None
        self.queue = Queue()
        self.paused = True
        self.queueThread = None
        self.progressBarThread = None
        self.currentPlaylist = None
        self.listWinStart = 0
        self.barWinProgress = 0
        self.albums: Dict[str, Album] = dict()
        self.insideAlbum = False
        self.configFile = os.path.join(pathsep.join(os.path.abspath(__file__).split(pathsep)[:-1]), "settings.config")

        if not os.path.isfile(self.configFile):
            # It's most likely the first time the user
            # opens the program, so it creates a default
            # config file and shows a welcome message

            Parser.writeConfigFile(self.configFile,
                                   {
                                       "musicFolder": str(os.path.join(Path.home(), "Music")),
                                       "volume": 25,
                                       "forwardSkip": 5,
                                       "backwardsSkip": 5,
                                       "random": False,
                                       "# Available Special Keys": "<UP> , <DOWN> , <LEFT> , <RIGHT> , "
                                                                   "<TAB> , <SPACE>",
                                       "ks_SongSelectionUp": "<UP>",
                                       "ks_VolumeUp": "<UP>",
                                       "ks_SongNext": "<RIGHT>",
                                       "ks_SongPrevious": "<LEFT>",
                                       "ks_SongSelectionDown": "<DOWN>",
                                       "ks_VolumeDown": "<DOWN>",
                                       "ks_MoveBetweenWins": "<TAB>",
                                       "ks_PlayPauseSong": "<SPACE>",
                                       "ks_Quit": "q",
                                       "ks_NewPlaylist": "n",
                                       "ks_AddToPlaylist": "+",
                                       "ks_RemoveFromPlaylist": "-",
                                       "ks_ChangeFolderSetting": "c",
                                       "ks_ChangeFlowSetting": "f",
                                       "ks_HelpMenu": "h",
                                       "ks_Queue": "p",
                                       "ks_ChangeMetadata": "m"
                                   })
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self.popupWin.border(']', '[', '=', '=', '+', '+', '+', '+')
            self.popupWin.addstr(2, 2, "Welcome to MusiCli",
                                 curses.color_pair(1))
            self.popupWin.addstr(5, 2, "Press \"H\" to view the keyboard shortcuts <Enter>")
            self.popupWin.refresh()
            self.stdscr.getstr(0, 0, 0)
            self.popupWin.clear()
            self.stdscr.clear()

        self.validSyntax = Parser.syntaxIsValid(self.configFile)
        self.configuration = Parser.readConfigFile(self.configFile)
        self.notParsedConfiguration = {k: v for k, v in self.configuration.items()}  # Clone without linking
        self.configuration = Parser.makeReadableByCode(self.configuration)

        # !!! Remove once you add resizability !!!
        if self.stdscr.getmaxyx()[0] < 28 or self.stdscr.getmaxyx()[1] < 130:
            raise Exception("Not enough space, please maximize terminal. If that doesn't work, try and "
                            "lower the font size")

        self.listWin, self.barWin, self.metaWin = self._generateWindows()
        self.selectedWin = self.listWin

        # Checks for missing songs inside playlists, as playlists can contain songs
        # from different folders, and trying to access a song that has been deleted
        # would crash the program
        missing = Parser.getSongsMissingFromPlaylist({k: v for k, v in self.configuration.items()
                                                      if k.startswith("playlist_")})
        if missing:
            for name, songs in missing.items():
                for song in songs:
                    self.configuration[name].remove(
                        os.path.join(self.configuration["musicFolder"], song))
            Parser.writeConfigFile(self.configFile,
                                   self.configuration)
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self._makeErrorPopup(self.popupWin, "Unaccessible songs were removed from playlists", "Playlists")

        # Checks if the configuration file is valid. If it's not it shows an error and quits
        if not self.validSyntax or not Parser.configurationIsValid(self.notParsedConfiguration):
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self._makeErrorPopup(self.popupWin, "Invalid configuration file", "Configuration")
            sys.exit(-1)

        self._refreshWindow(self.listWin)
        self._refreshWindow(self.barWin)
        self._refreshWindow(self.metaWin)
        self.selectableWins = [self.listWin, self.metaWin, self.barWin]
        self._changeVolume(self.configuration["volume"])

    def _generateWindows(self):
        """
        Summary:
        -------
        generates all the needed windows according to
        the current terminal size.

        Returns:
        -------
        List
            The generated windows
        """

        maxY, maxX = self.stdscr.getmaxyx()

        # Selected win
        # Bar win
        # Meta win
        return [curses.newwin(maxY - 2,
                              maxX // 3, 1, 1),

                curses.newwin(maxY // 5,
                              maxX // 3 * 2 - 3,
                              maxY - maxY // 5 - 1,
                              maxX // 3 + 2),

                curses.newwin((maxY // 5) * 4 + 2,
                              maxX // 3 * 2 - 3,
                              1,
                              maxX // 3 + 2)]

    def _refreshWindow(self, win):
        """
        Summary:
        -------
        refreshes a give window and adds its border back.

        Parameters:
        -------
        win : curses.window
            Thw window to refres
        """

        win.border('|', '|', '-', '-', '+', '+', '+', '+')
        if self.selectedWin == win:
            win.border(']', '[', '=', '=', '+', '+', '+', '+')
        win.refresh()
        self.stdscr.refresh()

    def _checkForInput(self):
        """
        Summary:
        -------
        the main event loop.
        Checks for keypresses.
        """

        key = self.stdscr.getch()

        # Quits the program
        if self.configuration["ks_Quit"] == key:
            self.stop()
            # raise KeyboardInterrupt()

        # Shows the help menu
        elif self.configuration["ks_HelpMenu"] == key:
            self._showHelpMenu()

        # Shows the queue
        elif self.configuration["ks_Queue"] == key:
            self._showQueue()

        # Add resizability
        elif curses.KEY_RESIZE == key:
            for window in self.selectableWins:
                del window

            self.listWin, self.barWin, self.metaWin = self._generateWindows()
            self.selectableWins = [self.listWin, self.metaWin, self.barWin]
            self.selectedWin = self.listWin
            self._refreshEverything()

        # Moves between windows
        elif self.configuration["ks_MoveBetweenWins"] == key:
            self.selectedWin = self.selectableWins[
                (self.selectableWins.index(self.selectedWin) + 1) % len(self.selectableWins)]
            self._refreshEverything()

        # Song Selection Window specific hotkeys
        if self.selectedWin == self.listWin:

            # Scrolls songs down
            if self.configuration["ks_SongSelectionDown"] == key:
                if self.insideAlbum:
                    self.listWinStart += 1 if self.listWinStart < len(self.albums.get(self.selectedAlbumName)) else 0
                    try:
                        self.selectedEntry = self.albums.get(self.selectedAlbumName)[self.listWinStart]
                    except IndexError:
                        self.listWinStart -= 1
                    self.listWin.clear()
                    self._populateSongs(self.listWin, self.albums.get(self.selectedAlbumName),
                                        start=self.listWinStart, insideAlbum=True)

                else:
                    self.listWinStart += 1 if self.listWinStart < len(list(self.albums.keys())) else 0
                    try:
                        self.selectedAlbumName = list(self.albums.keys())[self.listWinStart]
                    except IndexError:
                        self.listWinStart -= 1
                    self._populateSongs(self.listWin, self.albums, start=self.listWinStart)

                self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)
                self._refreshEverything()

            # Scrolls songs up
            elif self.configuration["ks_SongSelectionUp"] == key:
                if self.insideAlbum:
                    self.listWinStart -= 1 if self.listWinStart > 0 else 0
                    try:
                        self.selectedEntry = self.albums.get(self.selectedAlbumName)[self.listWinStart]
                    except IndexError:
                        self.listWinStart += 1
                    self.listWin.clear()
                    self._populateSongs(self.listWin, self.albums.get(self.selectedAlbumName),
                                        start=self.listWinStart, insideAlbum=True)

                else:
                    self.listWinStart -= 1 if self.listWinStart > 0 else 0
                    try:
                        self.selectedAlbumName = list(self.albums.keys())[self.listWinStart]
                    except IndexError:
                        self.listWinStart += 1
                    self._populateSongs(self.listWin, self.albums, start=self.listWinStart)

                self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)
                self._refreshEverything()

            # Plays the selected song
            elif self.configuration["ks_PlayPauseSong"] == key:
                if self.insideAlbum:
                    if self.selectedEntry == "..":
                        self.insideAlbum = False
                        self.listWinStart = 0
                        self.selectedAlbumName = list(self.albums.keys())[self.listWinStart]
                        self._populateSongs(self.listWin,
                                            self.albums,
                                            start=0,
                                            insideAlbum=False)
                        self._populateMetadata(self.metaWin,
                                               insideAlbum=False)
                        return

                    else:
                        try:
                            # To avoid having two conflicting threads
                            self.queueThread.kill()
                        except Exception:
                            pass

                        self.queue.index = 0
                        self.currentPlaylist = str(self.selectedEntry)[:-1] \
                            if f"playlist_{str(self.selectedEntry)[:-1]}" in self.configuration.keys() else None
                        self.queue = self._generateQueue(self.albums.get(self.selectedAlbumName),
                                                         start=self.albums.get(self.selectedAlbumName).index(self.selectedEntry))
                        self._playSong(song=self.queue[self.queue.index])

                else:
                    self.insideAlbum = True
                    self.listWinStart = 0
                    self.listWin.clear()
                    self.selectedEntry = self.albums.get(self.selectedAlbumName)[0]
                    self._populateSongs(self.listWin,
                                        self.albums.get(self.selectedAlbumName),
                                        start=self.albums.get(self.selectedAlbumName).index(self.selectedEntry),
                                        insideAlbum=True)
                    self._refreshEverything()

            # Creates a playlist
            elif self.configuration["ks_NewPlaylist"] == key:
                if self.insideAlbum:
                    self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                                  self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
                    self._makeErrorPopup(self.popupWin, "Return to album selection to create new playlist", "Error")
                    return

                self._createNewPlaylist()

            # Adds the selected song to a playlist
            elif self.configuration["ks_AddToPlaylist"] == key:
                self._addToPlaylist()

            # Removes the selected song from a playlist
            elif self.configuration["ks_RemoveFromPlaylist"] == key:
                self._removeFromPlaylist()

        # Metadata Window specific hotkeys
        elif self.selectedWin == self.metaWin:
            # Changes the song's Metadata:
            if self.configuration["ks_ChangeMetadata"] == key:
                self._changeMetadataFor(self.selectedEntry)
                self._refreshEverything()

            # Changes the music folder
            if self.configuration["ks_ChangeFolderSetting"] == key:
                self.metaWin.clear()
                self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum, promptingForFolder=True)
                curses.echo()
                newFolder = self.metaWin.getstr(self.metaWin.getmaxyx()[0] - 3, 2)
                curses.noecho()
                if not os.path.isdir(newFolder.decode()):
                    self._refreshEverything()
                    self._addError(self.metaWin, self.metaWin.getmaxyx()[0] - 4, 2, "Current Folder:",
                                   "Folder doesn't exist")
                    self._refreshWindow(self.metaWin)
                    return
                if not len(self._getMusic(folder=newFolder.decode())):
                    self._refreshEverything()
                    self._addError(self.metaWin, self.metaWin.getmaxyx()[0] - 4, 2, "Current Folder:",
                                   "Folder has no songs ")
                    self._refreshWindow(self.metaWin)
                    return

                self.configuration["musicFolder"] = newFolder.decode()
                self._refreshEverything()
                self.listWin.clear()
                self.listWinStart = 0
                # self.music = self._getMusic(folder=newFolder.decode())
                self._populateSongs(self.listWin,
                                    self.albums if not self.insideAlbum else self.albums.get(self.selectedAlbumName),
                                    self.listWinStart)
                self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)

            # Changes the song flow (Linear / Random)
            if self.configuration["ks_ChangeFlowSetting"] == key:
                if self.insideAlbum:
                    self.configuration["random"] = not self.configuration["random"]
                    self.queue = self._generateQueue(self.albums.get(self.selectedAlbumName),
                                                     start=self.albums.get(self.selectedAlbumName)[self.selectedEntry])
                    self.queue.index = 1  # Skip first song, it's already playing
                    if not self.configuration["random"]:
                        self.queue.index = self.albums.get(self.selectedAlbumName)[self.selectedEntry] + 1
                    self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)

        # Progress Bar Window specific hotkeys
        elif self.selectedWin == self.barWin:

            # Turns the volume down
            if self.configuration["ks_VolumeDown"] == key:
                if self.configuration["volume"] > 0:
                    self.configuration["volume"] -= 1
                    self._changeVolume(self.configuration["volume"])
                    self._refreshWindow(self.barWin)

            # Turns the volume up
            elif self.configuration["ks_VolumeUp"] == key:
                if self.configuration["volume"] < 100:
                    self.configuration["volume"] += 1
                    self._changeVolume(self.configuration["volume"])
                    self._refreshWindow(self.barWin)

            # Goes to the previous song
            if self.configuration["ks_SongPrevious"] == key:
                try:
                    self.queueThread.kill()
                except Exception:
                    pass
                self.queue.index = (self.queue.index - 1) % len(self.queue)
                if self.queue[self.queue.index] == "..":
                    self.queue.index = (self.queue.index - 1) % len(self.queue)
                while f"playlist_{str(self.queue[self.queue.index])[:-1]}" in self.configuration.keys():
                    self.queue.index = (self.queue.index - 1) % len(self.queue)
                self._playSong(song=self.queue[self.queue.index])

            # Goes to the next song
            elif self.configuration["ks_SongNext"] == key:
                try:
                    self.queueThread.kill()
                except Exception:
                    pass
                self.queue.index = (self.queue.index + 1) % len(self.queue)
                if self.queue[self.queue.index] == "..":
                    self.queue.index = (self.queue.index + 1) % len(self.queue)
                while f"playlist_{str(self.queue[self.queue.index])[:-1]}" in self.configuration.keys():
                    self.queue.index = (self.queue.index + 1) % len(self.queue)
                self._playSong(song=self.queue[self.queue.index])

            # Pauses / UnPauses the song
            elif self.configuration["ks_PlayPauseSong"] == key:
                if self.paused:
                    mixer.music.unpause()
                    self.barWin.clear()
                    self.paused = False
                else:
                    mixer.music.pause()
                    self.paused = True
                    self._refreshWindow(self.barWin)

    def _playSong(self, song=None, start=1.0):
        """
        Summary:
        -------
        plays a given song.

        Parameters:
        -------
        song : str
            The song to play. If None, the currently selected song plays

        start : float
            The start time of the song. If None, begin at the start of the song
        """

        # Currently selected song or "song" parameter
        self.selectedEntry = self.albums.get(self.selectedAlbumName)[self.listWinStart] if not song else song
        self.playingSong = self.selectedEntry

        # Automatically moves to the progress bar window
        self.selectedWin = self.barWin
        self._refreshEverything()
        mixer.music.stop()

        mixer.music.load(self.selectedEntry.path)

        # To avoid "pygame.error: Audio device hasn't been opened"
        while True:
            try:
                mixer.music.play(start=start)
                break
            except Exception:
                continue
        self.paused = False
        mixer.music.set_volume(self.configuration["volume"] / 100)
        self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)
        if self.insideAlbum:
            self._populateSongs(self.listWin, self.albums.get(self.selectedAlbumName), self.listWinStart,
                                insideAlbum=True)
        else:
            self._populateSongs(self.listWin, self.albums, self.listWinStart,
                                insideAlbum=False)

        if self.progressBarThread is not None:
            try:
                self.progressBarThread.terminate()
            except Exception as e:
                pass

        if self.queueThread is not None:
            try:
                self.queueThread.terminate()
            except Exception:
                pass

        self.progressBarThread = kthread.KThread(target=self._startProgressBar, kwargs={"song": song}, daemon=True)
        self.progressBarThread.start()

        if not self.queueThread:
            self.queueThread = kthread.KThread(target=self._queueHelper, daemon=True)
            self.queueThread.start()

    def _queueHelper(self):
        """
        Summary:
        -------
        the method used by the queueThread thread.
        Handles the queue.
        """

        # Generates a new queue
        self.queue = self._generateQueue(self.albums.get(self.selectedAlbumName),
                                         start=self.albums.get(self.selectedAlbumName).index(self.selectedEntry))
        self.queue.index = 0

        while True:
            while mixer.music.get_busy():
                continue

            self.queue.index = (self.queue.index + 1) % len(self.queue)
            if self.queue[self.queue.index] == "..":
                self.queue.index = (self.queue.index + 1) % len(self.queue)
            while f"playlist_{str(self.queue[self.queue.index])[:-1]}" in self.configuration.keys():
                self.queue.index = (self.queue.index + 1) % len(self.queue)

            self.barWinProgress = 0
            self.progressBarThread.terminate()
            self._playSong(song=self.queue[self.queue.index], start=0.0)

    def _generateQueue(self, songs, start=0) -> Queue:
        """
        Summary:
        -------
        generates a queue starting at a given index.

        Parameters:
        -------
        songs : List
            The songs to include in the queue

        start : int
            The index to start from

        Returns:
        -------
        List
            The generated queue
        """

        if not self.currentPlaylist:
            if len(songs) > 1:
                order = list(range(start, len(songs))) + list(range(0, start))
            else:
                order = [0]
            queue = [songs[i] for i in order if i < len(songs)]
            if self.configuration["random"]:
                random.shuffle(queue)
                queue[0] = self.selectedEntry
            return Queue(*queue)
        else:
            # The queue is the playlist itself
            music = self.configuration[f"playlist_{self.currentPlaylist}"]
            if self.configuration["random"]:
                random.shuffle(music)
            return Queue(*music)

    def _refreshEverything(self):
        """
        Summary:
        -------
        refreshes all visible windows
        """

        try:
            self.stdscr.clear()
            self.metaWin.clear()
            self.listWin.clear()
            self.barWin.clear()
            if mixer.music.get_busy():
                # A song is playing, don't reset the progress bar
                self._setProgressBar(int(self.barWinProgress))
            else:
                # No song is playing, progress bar can be reset
                self._setProgressBar(0)
            if self.insideAlbum:
                self._populateSongs(self.listWin, self.albums.get(self.selectedAlbumName), self.listWinStart, insideAlbum=True)
            else:
                self._populateSongs(self.listWin, self.albums, self.listWinStart, insideAlbum=False)
            self._refreshWindow(self.listWin)
            self._refreshWindow(self.barWin)
            self._refreshWindow(self.metaWin)
            self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)
            self._changeVolume(self.configuration["volume"])
        except Exception:
            pass

    def _getMusic(self, folder=None) -> List[Song]:
        """
        Summary:
        -------
        returns all songs inside a given folder.
        if folder is None, the folder is taken from the
        configuration file

        Parameters:
        -------
        folder : str
            The folder to check

        Returns:
        -------
        List
            All the songs that were found
        """

        if not folder:
            folder = self.configuration["musicFolder"]
        out = []
        for f in os.listdir(folder):
            if os.path.isdir(os.path.join(folder, f)):
                out.extend(self._getMusic(folder=os.path.join(folder, f)))
            elif f.split(".")[-1] in supportedExtensions:
                out.append(Song(os.path.join(folder, f)))
        return out

    @staticmethod
    def _getAlbums(songs) -> Dict:
        """
        Summary:
        -------
        classifies the given song list by album

        Parameters:
        -------
        songs : List
            The songs to classify

        Returns:
        -------
        Dict
            The classified songs
        """

        albums = {}
        for song in songs:
            key = song.album
            try:
                albums[key].append(song)
            except (AttributeError, KeyError):
                albums[key] = Album([song])

        for k in albums.keys():
            albums[k].append("..")
        return albums

    def start(self):
        """
        Summary:
        -------
        starts the program itself
        """

        music = self._getMusic()
        if not music:
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self._makeErrorPopup(self.popupWin, "No songs in default music folder", "Music Folder")
            sys.exit(-1)
        self.albums = self._getAlbums(music)
        self.selectedAlbumName = list(self.albums.keys())[0]

        self._populateSongs(self.listWin, self.albums, self.listWinStart)
        self.selectedEntry = self.albums[list(self.albums.keys())[self.listWinStart]]
        self.currentPlaylist = str(self.selectedEntry)[:-1] \
            if f"playlist_{str(self.selectedEntry)[:-1]}" in self.configuration.keys() else None

        self._populateMetadata(self.metaWin, insideAlbum=self.insideAlbum)
        self._setProgressBar(0)
        while True:
            self._checkForInput()

    def stop(self):
        """
        Summary:
        -------
        stops the program itself
        """

        # Saves the latest settings
        Parser.writeConfigFile(self.configFile,
                               self.configuration)
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        sys.exit(0)

    def _populateSongs(self, win, elements, start=2, insideAlbum=False):
        """
        Summary:
        -------
        adds a song list to a given window from a given index.

        Parameters:
        -------
        win : curses.windwo
            The window to put the songs on

        songs : List
            The songs to put on the winwo

        start : int
            The index to start displaying songs from

        insideAlbum : bool
            Wether or not the user is currently inside an album
        """

        x = 2
        y = 1
        for conf in self.configuration.keys():
            if conf.startswith("playlist_"):
                # Adds playlists that may have been left out
                if not conf[9:].strip() in self.albums.keys():
                    self.albums[conf[9:].strip()] = self.configuration[conf] + [".."]

        if insideAlbum:
            for i, song in enumerate(list(elements)[start:]):
                songName = song.title if isinstance(song, Song) else song
                if i == 0:
                    songName = "]-> " + songName
                win.addstr(y, x, songName[:(self.stdscr.getmaxyx()[1] // 3 - 1)])
                self._refreshWindow(win)
                y += 1

        else:
            for i, element in enumerate(list(elements)[start:]):
                if i == 0:
                    element = "]-> " + element
                win.addstr(y, x, element[:(self.stdscr.getmaxyx()[1] // 3 - 1)])
                self._refreshWindow(win)
                y += 1

    def _changeVolume(self, volume):
        """
        Summary:
        -------
        changes the song volume and displayes the changes.

        Parameters:
        -------
        volume : int
            The new volume
        """

        self.barWin.clear()
        self.barWin.addstr(2, self.barWin.getmaxyx()[1] - len("Volume") - 1, f"Volume", curses.color_pair(1))
        self.barWin.addstr(3, self.barWin.getmaxyx()[1] - 5, f"{volume}%")

        # Usually it should be divided by 100,
        # But on my test machine the volume was extremely high
        mixer.music.set_volume(self.configuration["volume"] / 500)

    def _startProgressBar(self, song=None):
        """
        Summary:
        -------
        starts the progress bar movement.

        Parameters:
        -------
        song : str
            The song playing
        """

        index = self.barWinProgress
        length = song.length

        self.barWin.addstr(2, 1, f"Progress", curses.color_pair(1))
        self._refreshWindow(self.barWin)
        while mixer.music.get_busy():
            # Don't do anything while the song is paused
            if self.paused:
                continue

            self._setProgressBar(int(index))
            self.barWinProgress = self.queue.index
            time.sleep(1)
            index += (self.barWin.getmaxyx()[1] - 5) / length

    def _setProgressBar(self, progress):
        """
        Summary:
        -------
        sets the progress bar progress.

        Parameters:
        -------
        progress : int
            The progress to display
        """

        self.barWin.clear()
        self._changeVolume(self.configuration["volume"])
        self.barWin.addstr(1, 1, "Playing: ", curses.color_pair(1))
        self.barWin.addstr(1, len("Playing: ") + 1, os.path.basename(self.playingSong.title)[:50] if self.playingSong else "")

        if self.paused and mixer.music.get_busy():
            self.barWin.addstr(2, self.barWin.getmaxyx()[1] // 2 - len(f"Paused") // 2, f"Paused", curses.color_pair(1))

        self.barWin.addstr(2, 1, f"Progress", curses.color_pair(1))
        self.barWin.addstr(3, 1, "#" * progress)
        self._refreshWindow(self.barWin)

    def _addMetadata(self, win, y, x, tag, value):
        """
        Summary:
        -------
        helper function to add information to a window.

        Parameters:
        -------
        win : curses.window
            The window to put the information on

        y : int
            The y coordinate

        x : int
            The x coordinate

        tag : str
            The title

        value : str
            The information itself
        """

        win.addstr(y, x, tag, curses.color_pair(1))
        win.addstr(y + 1, x, value)
        self._refreshWindow(win)

    def _addError(self, win, y, x, tag, value):
        """
        Summary:
        -------
        helper function to add an error to a window.

        Parameters:
        -------
        win : curses.window
            The window to put the error on

        y : int
            The y coordinate

        x : int
            The x coordinate

        tag : str
            The title

        value : str
            The error itself
        """

        win.addstr(y, x, tag, curses.color_pair(1))
        win.addstr(y + 1, x, value, curses.color_pair(2))
        self._refreshWindow(win)

    def _populateMetadata(self, win, promptingForFolder=False, insideAlbum=False):
        """
        Summary:
        -------
        fills a window with the information on the currently selected song.
0
        Parameters:
        -------
        win : curses.window
            The window to put the information on

        promptingForFolder : bool
            Wether or not to write the current folder path.
            This is set to True when the user is changing the folder

        insideAlbum : bool
            Wether or not the user is currently inside an album
        """

        win.clear()

        albumName = self.selectedAlbumName
        first = Figlet(font="colossal").renderText(albumName[0].upper())
        rest = Figlet(font="basic").renderText(albumName[1:])

        difference = len(first.split("\n")) - len(rest.split("\n"))
        logo = "\n".join(first.split("\n")[:difference]) + "\n"
        for i, line in enumerate(rest.split("\n")):
            logo += first.split("\n")[(difference + i - 1) % len(first.split("\n"))] + line + "\n"

        try:
            for i, line in enumerate(logo.split("\n")):
                win.addstr(win.getmaxyx()[0] - len(logo.split("\n")) + i,
                           (win.getmaxyx()[1] - len(logo.split("\n")[len(logo.split("\n")) // 2])) // 2,
                           line,
                           curses.color_pair(3))
        except Exception:
            win.clear()
            rest = Figlet(font="basic").renderText(f"{albumName[1:3]} . . .")
            difference = len(first.split("\n")) - len(rest.split("\n"))
            logo = "\n".join(first.split("\n")[:difference]) + "\n"
            for i, line in enumerate(rest.split("\n")):
                logo += first.split("\n")[(difference + i - 1) % len(first.split("\n"))] + line + "\n"

            for i, line in enumerate(logo.split("\n")):
                win.addstr(10 + i,
                           (win.getmaxyx()[1] - len(logo.split("\n")[len(logo.split("\n")) // 2])) // 2,
                           line,
                           curses.color_pair(3))
        # The song is a single song
        if insideAlbum:
            win.clear()
            if self.selectedEntry != "..":
                # All these try except are really ugly
                # I should find a better way, but this works
                # as a temporary solution
                changeMetaKey = None
                for key, value in self.notParsedConfiguration.items():
                    if key == "ks_ChangeMetadata":
                        changeMetaKey = value

                self._addMetadata(win, 1, 2, "Metadata:", f"(Change: {changeMetaKey})")
                try:
                    self._addMetadata(win, 4, 2, "Title:", os.path.basename(self.selectedEntry.title))
                except Exception:
                    self._addMetadata(win, 4, 2, "Title:", os.path.basename(self.selectedEntry[:-4]))
                try:
                    self._addMetadata(win, 7, 2, "Artist:", self.selectedEntry.artist)
                except Exception:
                    self._addMetadata(win, 7, 2, "Artist:", "<Unknown>")
                try:
                    self._addMetadata(win, 10, 2, "Track #n:", self.selectedEntry.track + " / " + self.selectedEntry.track_total)
                except Exception:
                    self._addMetadata(win, 10, 2, "Track #n:", "1 / 1")
                try:
                    self._addMetadata(win, 13, 2, "Album:", self.selectedEntry.album)
                except Exception:
                    self._addMetadata(win, 13, 2, "Album:", "<Unknown>")

            else:
                self._addMetadata(win, 1, 2, "Type:", "Wildcard")
                self._addMetadata(win, 4, 2, "Action:", "Go back")

        else:
            # The song is a playlist
            if f"playlist_{self.selectedAlbumName}" in self.configuration.keys():
                self._addMetadata(win, 1, 2, "Type:", "Playlist")
                self._addMetadata(win, 4, 2, "Title:", self.selectedAlbumName)
                win.addstr(7, 2, "Songs:", curses.color_pair(1))
                i = 8
                try:
                    for index, song in enumerate(self.configuration[f"playlist_{self.selectedAlbumName}"]):
                        if index == 7:
                            break
                        win.addstr(i, 2, song[:-4])
                        i += 1
                    self._refreshWindow(win)
                except Exception:
                    pass

            # The song is an album
            else:
                albumName = self.selectedAlbumName
                firstSong = self.albums[albumName][0]
                self._addMetadata(win, 1, 2, "Type:", "Album")
                self._addMetadata(win, 4, 2, "Title:", albumName)
                try:
                    self._addMetadata(win, 7, 2, "Artist:", firstSong.artist)
                except Exception:
                    self._addMetadata(win, 7, 2, "Artist:", "<Unknown>")

        # Adds global settings (Flow, Folder)
        self._addMetadata(win, win.getmaxyx()[0] - 7, 2, "Song Flow:",
                          "Random (Change: f)" if self.configuration["random"] else "Linear (Change: f)")

        if promptingForFolder:
            self._addMetadata(win, win.getmaxyx()[0] - 4, 2, "Current Folder:",
                              "")
            return

        self._addMetadata(win, win.getmaxyx()[0] - 4, 2, "Current Folder:",
                          self.configuration["musicFolder"] + " (Change: c)")

    @staticmethod
    def _createPrompt(win, title, prompt):
        """
        Summary:
        -------
        helper function to prompt the user for a value.

        Parameters:
        -------
        win : curses.window
            The windows to display the prompt on

        title : str
            The popup title

        prompt : str
            The prompt

        Returns:
        -------
        str
            The value given by the user
        """

        win.border(']', '[', '=', '=', '+', '+', '+', '+')
        win.addstr(2, 2, title,
                   curses.color_pair(1))
        win.addstr(5, 2, prompt)
        win.refresh()
        curses.echo()
        value = "".join([char for char in win.getstr(5, 2 + len(prompt)).decode() if
                         char in string.ascii_letters + string.digits])
        curses.noecho()
        win.clear()
        win.refresh()
        return value

    def _createNewPlaylist(self):
        """
        Summary:
        -------
        prompts the user to create a new playlist
        """

        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
        name = self._createPrompt(self.popupWin, "Create New Playlist", "Name: ")

        if not name:
            self._makeErrorPopup(self.popupWin, "Invalid name", "Create New Playlist")
            return

        self.popupWin.clear()
        self.popupWin.refresh()
        self.configuration[f"playlist_{name}"] = []
        self._refreshEverything()

    def _addToPlaylist(self):
        """
        Summary:
        -------
        prompts the user to add the currently selected song
        to a playlist
        """

        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
        playlist = self._createPrompt(self.popupWin, "Add to Playlist", "Playlist: ")

        if not playlist:
            self._makeErrorPopup(self.popupWin, "No name", "Add to Playlist")
            return

        if f"playlist_{playlist}" not in self.configuration.keys():
            self._makeErrorPopup(self.popupWin, "Playlist doesn't exist", "Add to Playlist")
            return

        if f"playlist_{str(self.selectedEntry)[:-1]}" in self.configuration.keys():
            self._makeErrorPopup(self.popupWin, "Recursion error", "Add to Playlist")
            return

        if isinstance(self.selectedEntry, (list, tuple, slice)):
            self._makeErrorPopup(self.popupWin, "Cannot add album to playlist", "Add to Playlist")
            self._refreshEverything()
            return

        if os.path.join(self.configuration["musicFolder"], self.selectedEntry.path) \
                in self.configuration[f"playlist_{playlist}"]:
            self._makeErrorPopup(self.popupWin, "Song already is in playlist", "Add to Playlist")
            self._refreshEverything()
            return

        self.popupWin.clear()
        self.popupWin.refresh()
        self.configuration[f"playlist_{playlist}"].append(
            os.path.join(self.configuration["musicFolder"], self.selectedEntry.path))
        self._refreshEverything()

    def _removeFromPlaylist(self):
        """
        Summary:
        -------
        prompts the user to remove the currently selected song
        from a playlist
        """

        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)

        albumName = list(self.albums.keys())[self.listWinStart]
        if f"playlist_{albumName}" in self.configuration.keys():
            self.popupWin.clear()
            self.popupWin.border(']', '[', '=', '=', '+', '+', '+', '+')
            self.popupWin.refresh()
            self.popupWin.addstr(2, 2, "Remove from Playlist",
                                 curses.color_pair(1))
            self.popupWin.addstr(5, 2, "Remove Playlist? <Y/N>", curses.color_pair(2))
            curses.echo()
            if self.popupWin.getstr(6, 2, 1).decode().lower() == "y":
                del self.configuration[f"playlist_{albumName}"]
                del self.albums[albumName]
                self.listWinStart = 0
            curses.noecho()
            self.popupWin.refresh()
            self.popupWin.clear()
            self._refreshEverything()
            return

        playlist = self._createPrompt(self.popupWin, "Remove from Playlist", "Playlist: ")

        if not playlist:
            self._makeErrorPopup(self.popupWin, "No name", "Remove from Playlist")
            return

        if isinstance(self.selectedEntry, (list, tuple, slice)):
            self._makeErrorPopup(self.popupWin, "Cannot remove album from playlist", "Remove from Playlist")
            self._refreshEverything()
            return

        if f"playlist_{playlist}" not in self.configuration.keys():
            self._makeErrorPopup(self.popupWin, "Playlist doesn't exist", "Remove from Playlist")
            return

        if os.path.join(self.configuration["musicFolder"], self.selectedEntry) \
                not in self.configuration[f"playlist_{playlist}"]:
            self._makeErrorPopup(self.popupWin, "Song is not in playlist", "Remove from Playlist")
            return

        self.popupWin.clear()
        self.popupWin.refresh()
        self.configuration[f"playlist_{playlist}"].remove(
            os.path.join(self.configuration["musicFolder"], self.selectedEntry))
        self._refreshEverything()

    def _makeErrorPopup(self, win, message, title):
        """
        Summary:
        -------
        creates an error popup on a given window.

        Parameters:
        -------
        win : curses.window
            The window to put the popup on

        message : str
            The error message

        title : str
            The error title
        """
        win.clear()
        win.border(']', '[', '=', '=', '+', '+', '+', '+')
        win.refresh()
        win.addstr(2, 2, title, curses.color_pair(1))
        win.addstr(5, 2, f"{message} <Enter>", curses.color_pair(2))
        win.refresh()
        win.getstr(0, 0, 0)
        win.clear()
        self._refreshEverything()

    def _makeInfoPopup(self, win, message, title):
        """
        Summary:
        -------
        creates an information popup on a given window.

        Parameters:
        -------
        win : curses.window
            The window to put the popup on

        message : str
            The info message

        title : str
            The title
        """
        win.clear()
        win.border(']', '[', '=', '=', '+', '+', '+', '+')
        win.refresh()
        win.addstr(2, 2, title, curses.color_pair(1))
        win.addstr(5, 2, f"{message} <Enter>")
        win.refresh()
        win.getstr(0, 0, 0)
        win.clear()
        self._refreshEverything()

    def _showQueue(self):
        """
        Summary:
        shows a window with the current queue
        """

        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 2, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
        self.popupWin.border(']', '[', '=', '=', '+', '+', '+', '+')
        self.popupWin.addstr(2, 2, "Song queue: <Enter>",
                             curses.color_pair(1))

        y = 0
        x = 2
        for element in self.queue.allSongs:
            if not element == "..":
                self.popupWin.addstr(y + 4, x, f"{os.path.basename(element)}")
                y += 1
                if y >= 10:
                    y = 0
                    x += 35

        self.popupWin.refresh()
        self.popupWin.getstr(0, 0, 0)
        self.popupWin.clear()
        self._refreshEverything()

    def _showHelpMenu(self):
        """
        Summary:
        shows a menu with all the hotkeys specified in the config file
        """

        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 2, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
        self.popupWin.border(']', '[', '=', '=', '+', '+', '+', '+')
        self.popupWin.addstr(2, 2, "Keyboard Shortcuts: <Enter>",
                             curses.color_pair(1))

        y = 0
        x = 2
        for key, value in self.notParsedConfiguration.items():
            if key.startswith("ks_"):
                self.popupWin.addstr(y + 4, x, f"{key[3:]} = {value}")
                y += 1
                if y >= 10:
                    y = 0
                    x += 35

        self.popupWin.refresh()
        self.popupWin.getstr(0, 0, 0)
        self.popupWin.clear()
        self._refreshEverything()

    def _changeMetadataFor(self, song):
        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
        newTitle = self._createPrompt(self.popupWin, "Change song Title", f"Default \"{song.title}\": ")
        newArtist = self._createPrompt(self.popupWin, "Change song Artist", f"Default \"{song.artist}\": ")
        newAlbum = self._createPrompt(self.popupWin, "Change song Album", f"Default \"{song.album}\": ")

        song.title = newTitle if len(newTitle.strip()) else song.title
        song.artist = newArtist if len(newArtist.strip()) else song.artist
        song.album = newAlbum if len(newAlbum.strip()) else song.album

        if self.progressBarThread is not None:
            try:
                self.progressBarThread.terminate()
            except Exception as e:
                pass

        if self.queueThread is not None:
            try:
                self.queueThread.terminate()
            except Exception:
                pass
        mixer.music.stop()
        mixer.music.unload()

        if newAlbum != song.album and len(newAlbum.strip()):
            music = self._getMusic()
            if not music:
                self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                              self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
                self._makeErrorPopup(self.popupWin, "No songs in default music folder", "Music Folder")
                sys.exit(-1)
            self.albums = self._getAlbums(music)
            self.selectedAlbumName = list(self.albums.keys())[list(self.albums.keys()).index(newAlbum)]


def main(stdscr):
    p = Player(stdscr)
    try:
        p.start()
    except KeyboardInterrupt:
        p.stop()


if __name__ == '__main__':
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
