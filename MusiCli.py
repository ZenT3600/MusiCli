import os
import glob
import curses
import sys
import re
import ast
import time
import random
import kthread
import string

from pathlib import Path
from tinytag import TinyTag
from mutagen.mp3 import MP3
from pygame import mixer
from typing import Dict, List

"""
d888888b  .d88b.  d8888b.  .d88b.        db      d888888b .d8888. d888888b 
`~~88~~' .8P  Y8. 88  `8D .8P  Y8.       88        `88'   88'  YP `~~88~~' 
   88    88    88 88   88 88    88       88         88    `8bo.      88    
   88    88    88 88   88 88    88       88         88      `Y8b.    88    
   88    `8b  d8' 88  .8D `8b  d8'       88booo.   .88.   db   8D    88    
   YP     `Y88P'  Y8888D'  `Y88P'        Y88888P Y888888P `8888Y'    YP    


    To Add:
        * Add Resizability                              Importance: MEDIUM
        * Faster refresh rate                           Importance: LOW

    Feature Ideas:
        * Modify a song metadata
        * Move forward and backwards in a song
        * Add bookmarks on a song
        * Albums support
        * Look in subfolders of ~/Music
"""

pathsep = os.path.sep


def syntaxIsValid(file: str) -> bool:
    """
    Summary:
    -------
    parses a file and searches for errors in the syntax.

    Parameters:
    -------
    file : str
        The file to parse

    Returns:
    -------
    bool
        Wether the file is syntactically valid or not
    """

    with open(file, "r") as f:
        try:
            [line.split(" :=: ") for line in f.readlines() if len(line.strip())]
        except Exception:
            return False
    return True


def readConfigFile(file: str) -> Dict:
    """
    Summary:
    -------
    parses a file and returns a dictionary with the
    corresponding values.

    Parameters:
    -------
    file : str
        The file to parse

    Returns:
    -------
    Dict
        The parsed dictionary
    """

    data = {}
    with open(file, "r") as f:
        lines = [line.split(" :=: ") for line in f.readlines() if line.strip()]

    for line in lines:
        if line[0].startswith("#"):
            continue

        if line[1].strip().startswith("\"") and line[1].strip().endswith("\""):
            data[line[0].strip()] = re.search('\"(.+?)\"', line[1].strip()).group(1)

        elif line[1].strip().startswith("[") and line[1].strip().endswith("]"):
            parsableString = line[1].strip()
            parsableString = parsableString.replace("true", "True")
            parsableString = parsableString.replace("false", "False")
            parsableString = parsableString.replace("none", "None")
            data[line[0].strip()] = [item for item in ast.literal_eval(parsableString)]

        else:
            if line[1].strip() == "true":
                data[line[0].strip()] = True
            elif line[1].strip() == "false":
                data[line[0].strip()] = False
            elif line[1].strip() == "none":
                data[line[0].strip()] = None
            else:
                data[line[0].strip()] = int(line[1].strip())

    return data


def writeConfigFile(file: str, data: Dict):
    """
    Summary:
    -------
    writes a dictionary into a config file.

    Parameters:
    -------
    file : str
        The file to write to

    data : Dict
        The actual data to write to the file
    """

    AVAILABLE_SPECIAL = {v: k for k, v in {"<UP>": curses.KEY_UP,
                                           "<DOWN>": curses.KEY_DOWN,
                                           "<LEFT>": curses.KEY_LEFT,
                                           "<RIGHT>": curses.KEY_RIGHT,
                                           "<TAB>": 9,
                                           "<SPACE>": ord(" ")}.items()}

    text = ""
    with open(file, "w") as f:
        for key, value in data.items():
            if isinstance(value, (list, tuple)):
                text += f"{key} :=: {value}\n"

            elif isinstance(value, bool):
                if value:
                    text += f"{key} :=: true\n"
                elif not value:
                    text += f"{key} :=: false\n"
                elif value is None:
                    text += f"{key} :=: none\n"

            elif isinstance(value, (str, int)) and not isinstance(value, bool):
                if key.startswith("ks_"):
                    try:
                        if chr(value) in string.ascii_letters + string.digits + string.punctuation:
                            text += f"{key} :=: \"{chr(value)}\"\n"
                        elif value in AVAILABLE_SPECIAL.keys():
                            text += f"{key} :=: \"{AVAILABLE_SPECIAL[value]}\"\n"
                        else:
                            raise Exception()
                    except Exception:
                        text += f"{key} :=: \"{value}\"\n"
                else:
                    if isinstance(value, int):
                        text += f"{key} :=: {value}\n"
                    else:
                        text += f"{key} :=: \"{value}\"\n"
            else:
                text += f"{key} :=: {value}\n"

        f.write(text)


def configurationIsValid(configuration: Dict) -> bool:
    """
    Summary:
    -------
    parses a file and searches for errors in the hotkey configuration.

    Parameters:
    -------
    file : str
        The file to parse

    Returns:
    -------
    bool
        Wether the file's configuration is valid or not
    """

    AVAILABLE_SPECIAL = ["<UP>", "<DOWN>", "<LEFT>", "<RIGHT>", "<TAB>", "<SPACE>"]
    for key, value in configuration.items():
        if key.startswith("ks_"):
            if len(value) > 1:
                if value not in AVAILABLE_SPECIAL:
                    return False

            elif len(value) == 1:
                if value not in string.ascii_letters + string.digits + string.punctuation:
                    return False

            else:
                return False

    return True


def makeReadableByCode(data: Dict) -> Dict:
    """
    Summary:
    -------
    converts a .config-like dictionary into something the code can use.

    Parameters:
    -------
    data : Dict
        The dictionary to convert

    Returns:
    -------
    Dict
        The resulting dictionary
    """

    AVAILABLE_SPECIAL = {"<UP>": curses.KEY_UP,
                         "<DOWN>": curses.KEY_DOWN,
                         "<LEFT>": curses.KEY_LEFT,
                         "<RIGHT>": curses.KEY_RIGHT,
                         "<TAB>": 9,
                         "<SPACE>": ord(" ")}

    for key, value in data.items():
        if key.startswith("ks_"):
            if value in AVAILABLE_SPECIAL.keys():
                data[key] = AVAILABLE_SPECIAL[value]
            else:
                data[key] = ord(value)

        else:
            try:
                data[key] = int(value)
            except Exception:
                data[key] = value

    return data


def getSongsMissingFromPlaylist(playlists: Dict) -> Dict:
    """
    Summary:
    -------
    checks if the songs in the given playlists still exist.

    Parameters:
    -------
    playlists : Dict
        The playlists to check

    Returns:
    -------
    Dict
        The missing songs ordered by corresponding playlist
    """

    missing = {}
    for name, playlist in playlists.items():
        for song in playlist:
            if not os.path.isfile(song):
                try:
                    missing[name].append(song)
                except Exception:
                    missing[name] = [song]

    return missing


class Player:
    """
    A class used to represent the music player

    Attributes:
    -------
    stdscr : curses.window
        The main window object.

    listWin : curses.window
        The window object representing the song list window.

    metaWin : curses.window
        Thw window object representing the metadata window.

    barWin : curses.window
        The window object representing the progress bar window.

    popupWin : curses.window
        The window object representing all popup windows.

    playingSong : str
        The path to the song that's currently playing.

    selectedSong : str
        The path to the song that's currently selected, but
        not necessarily playing.

    currentPlaylist : str
        If the song playing is not part of a playlist the value is None.
        If the song playing is part of a playlist the value is the song itself.

    queue : List
        The current playing queue

    queueIndex : int
        The current position in the queue

    paused : bool
        Is the current playing song paused?

    queueThread : kthread.KThread
        The killable thread object that handles the queue

    progressBarThread : kthread.KThread
        The killable thread object that handles the progress bar movement

    listWinStart : int
        The index to start displaying songs in the songs list from

    barWinProgress : int
        The progress of the progress bar, measured in number of characters

    music : List
        All the available songs and playlists

    configFile : str
        The config file path

    invalidSyntax : bool
        Is the current config file syntactically correct?

    configuration : Dict
        The parsed configuration file.
        Gets parsed a second time to be readable by the code

    notParsedConfiguration : Dict
        The parsed configuration file.
        Stays intact

    selectedWin : curses.window
        The currently selected window

    selectableWins : List
        All the windows that can be selected
    """

    def __init__(self, stdscr):
        self.stdscr = stdscr
        #self.stdscr = curses.initscr()
        curses.noecho()
        curses.cbreak()
        curses.resize_term(*self.stdscr.getmaxyx())
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        self.stdscr.keypad(True)
        mixer.init()

        self.playingSong = None
        self.selectedSong = None
        self.currentPlaylist = None
        self.queue = list()
        self.queueIndex = 0
        self.paused = True
        self.queueThread = None
        self.progressBarThread = None
        self.listWinStart = 0
        self.barWinProgress = 0
        self.music = list()
        self.configFile = os.path.join(pathsep.join(os.path.abspath(__file__).split(pathsep)[:-1]), "settings.config")

        if not os.path.isfile(self.configFile):
            # It's most likely the first time the user
            # opens the program, so it creates a default
            # config file and shows a welcome message

            writeConfigFile(self.configFile,
                            {
                                "musicFolder": str(os.path.join(Path.home(), "Music")),
                                "volume": 25,
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

        self.validSyntax = syntaxIsValid(self.configFile)
        self.configuration = readConfigFile(self.configFile)
        self.notParsedConfiguration = {k: v for k, v in self.configuration.items()}  # Clone without linking
        self.configuration = makeReadableByCode(self.configuration)

        # !!! Remove once you add resizability !!!
        if self.stdscr.getmaxyx()[0] < 28 or self.stdscr.getmaxyx()[1] < 130:
            raise Exception("Not enough space, please maximize terminal. If that doesn't work, try and "
                            "lower the font size")
        maxY, maxX = self.stdscr.getmaxyx()
        self.selectedWin = self.listWin = curses.newwin(maxY - 2, maxX // 3, 1, 1)
        self.barWin = curses.newwin(maxY // 5, maxX // 3 * 2 - 3, maxY - maxY // 5 - 1, maxX // 3 + 2)
        self.metaWin = curses.newwin((maxY // 5) * 4 + 1, maxX // 3 * 2 - 3, 1, maxX // 3 + 2)
        self.popupWin = None

        # Checks for missing songs inside playlists, as playlists can contain songs
        # from different folders, and trying to access a song that has been deleted
        # would crash the program
        missing = getSongsMissingFromPlaylist({k: v for k, v in self.configuration.items()
                                               if k.startswith("playlist_")})
        if missing:
            for name, songs in missing.items():
                for song in songs:
                    self.configuration[name].remove(
                        os.path.join(self.configuration["musicFolder"], song))
            writeConfigFile(self.configFile,
                            self.configuration)
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self._makeErrorPopup(self.popupWin, "Unaccessible songs were removed from playlists", "Playlists")

        # Checks if the configuration file is valid. If it's not it shows an error and quits
        if not self.validSyntax or not configurationIsValid(self.notParsedConfiguration):
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self._makeErrorPopup(self.popupWin, "Invalid configuration file", "Configuration")
            sys.exit(-1)

        self._refreshWindow(self.listWin)
        self._refreshWindow(self.barWin)
        self._refreshWindow(self.metaWin)
        self.selectableWins = [self.listWin, self.metaWin, self.barWin]
        self._changeVolume(self.configuration["volume"])

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
            raise KeyboardInterrupt()

        # Shows the help menu
        elif self.configuration["ks_HelpMenu"] == key:
            self._showHelpMenu()

        # !!! Add resizability !!!
        elif curses.KEY_RESIZE == key:
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
                if self.music[self.listWinStart] != self.music[-1]:
                    self.listWinStart += 1
                    self.selectedSong = self.music[self.listWinStart]
                    self.currentPlaylist = self.selectedSong[:-1] \
                        if f"playlist_{self.selectedSong[:-1]}" in self.configuration.keys() else None
                    self._populateMetadata(self.metaWin)
                    self._refreshEverything()

            # Scrolls songs up
            elif self.configuration["ks_SongSelectionUp"] == key:
                if self.music[self.listWinStart] != self.music[0]:
                    self.listWinStart -= 1
                    self.selectedSong = self.music[self.listWinStart]
                    self.currentPlaylist = self.selectedSong[:-1] \
                        if f"playlist_{self.selectedSong[:-1]}" in self.configuration.keys() else None
                    self._populateMetadata(self.metaWin)
                    self._refreshEverything()

            # Plays the selected song
            elif self.configuration["ks_PlayPauseSong"] == key:
                try:
                    # To avoid having two conflicting threads
                    self.queueThread.kill()
                except Exception:
                    pass

                self.queueIndex = 0
                self.currentPlaylist = self.selectedSong[:-1] \
                    if f"playlist_{self.selectedSong[:-1]}" in self.configuration.keys() else None
                self.queue = self._generateQueue(start=self.music.index(self.selectedSong))
                self._playSong(song=self.queue[self.queueIndex])

            # Creates a playlist
            elif self.configuration["ks_NewPlaylist"] == key:
                self._createNewPlaylist()

            # Adds the selected song to a playlist
            elif self.configuration["ks_AddToPlaylist"] == key:
                self._addToPlaylist()

            # Removes the selected song from a playlist
            elif self.configuration["ks_RemoveFromPlaylist"] == key:
                self._removeFromPlaylist()

        # Metadata Window specific hotkeys
        elif self.selectedWin == self.metaWin:

            # Changes the music folder
            if self.configuration["ks_ChangeFolderSetting"] == key:
                self.metaWin.clear()
                self._populateMetadata(self.metaWin, promptingForFolder=True)
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
                self.music = self._getMusic(folder=newFolder.decode())
                self._populateSongs(self.listWin, self.music, self.listWinStart)
                self.selectedSong = self.music[self.listWinStart]
                self._populateMetadata(self.metaWin)

            # Changes the song flow (Linear / Random)
            if self.configuration["ks_ChangeFlowSetting"] == key:
                self.configuration["random"] = not self.configuration["random"]
                self.queue = self._generateQueue(start=self.music.index(os.path.basename(self.selectedSong)))
                self.queueIndex = 1  # Skip first song, it's already playing
                if not self.configuration["random"]:
                    self.queueIndex = self.music.index(self.selectedSong) + 1
                self._populateMetadata(self.metaWin)

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
                self.queueIndex = (self.queueIndex - 1) % len(self.queue)
                while f"playlist_{self.queue[self.queueIndex][:-1]}" in self.configuration.keys():
                    self.queueIndex = (self.queueIndex - 1) % len(self.queue)
                self._playSong(song=self.queue[self.queueIndex])

            # Goes to the next song
            elif self.configuration["ks_SongNext"] == key:
                try:
                    self.queueThread.kill()
                except Exception:
                    pass
                self.queueIndex = (self.queueIndex + 1) % len(self.queue)
                while f"playlist_{self.queue[self.queueIndex][:-1]}" in self.configuration.keys():
                    self.queueIndex = (self.queueIndex + 1) % len(self.queue)
                self._playSong(song=self.queue[self.queueIndex])

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

    def _playSong(self, song=None, noQueueThread=False):
        """
        Summary:
        -------
        plays a given song.

        Parameters:
        -------
        song : str
            The song to play. If None, the currently selected song plays

        fullPath : bool
            Wether the given song path is absolute or not

        noQueueThread : bool
            Wether or not to start a queueThread
        """

        # Currently selected song or "song" parameter
        self.selectedSong = self.music[self.listWinStart] if song is None else song
        self.playingSong = self.selectedSong

        # Automatically moves to the progress bar window
        self.selectedWin = self.barWin
        self._refreshEverything()
        mixer.music.stop()

        try:
            mixer.music.load(self.selectedSong)
        except Exception:
            mixer.music.load(os.path.join(self.configuration["musicFolder"], self.selectedSong))

        mixer.music.play()
        self.paused = False
        mixer.music.set_volume(self.configuration["volume"] / 100)
        self._populateMetadata(self.metaWin)
        self._populateSongs(self.listWin, self.music, self.listWinStart)
        try:
            self.progressBarThread.kill()
        except Exception:
            pass
        self.progressBarThread = kthread.KThread(target=self._startProgressBar, kwargs={"song": song})
        self.progressBarThread.start()

        if not self.queueThread and not noQueueThread:
            self.queueThread = kthread.KThread(target=self._queueHelper)
            self.queueThread.start()

    def _queueHelper(self):
        """
        Summary:
        -------
        the method used by the queueThread thread.
        Handles the queue.
        """

        # Generates a new queue
        self.queue = self._generateQueue(start=self.music.index(os.path.basename(self.selectedSong)))
        self.queueIndex = 0

        while True:
            while mixer.music.get_busy():
                continue

            self.queueIndex = (self.queueIndex + 1) % len(self.queue)
            self._playSong(song=self.queue[self.queueIndex],
                           noQueueThread=True)

    def _generateQueue(self, start=0) -> List:
        """
        Summary:
        -------
        generates a queue starting at a given index.

        Parameters:
        -------
        start : int
            The index to start from

        Returns:
        -------
        List
            The generated queue
        """

        if not self.currentPlaylist:
            music = self.music
            if len(music) > 1:
                order = list(range(start, len(music))) + list(range(0, start))
            else:
                order = [0]
            queue = [music[i] for i in order if i < len(music)]
            if self.configuration["random"]:
                random.shuffle(queue)
                queue[0] = self.selectedSong
            return queue
        else:
            # The queue is the playlist itself
            music = self.configuration[f"playlist_{self.currentPlaylist}"]
            if self.configuration["random"]:
                random.shuffle(music)
            return music

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
            self._populateSongs(self.listWin, self.music, self.listWinStart)
            self._refreshWindow(self.listWin)
            self._refreshWindow(self.barWin)
            self._refreshWindow(self.metaWin)
            self._populateMetadata(self.metaWin)
            self._changeVolume(self.configuration["volume"])
        except Exception:
            pass

    def _getMusic(self, folder=None) -> List:
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

        return [file.split(pathsep)[-1] for file in glob.glob(os.path.join(self.configuration['musicFolder']
                                                                           if not folder else folder, "*.mp3"))]

    def start(self):
        """
        Summary:
        -------
        starts the program itself
        """

        self.music = self._getMusic()
        if not self.music:
            self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                          self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
            self._makeErrorPopup(self.popupWin, "No songs in default music folder", "Music Folder")
            sys.exit(-1)

        self._populateSongs(self.listWin, self.music, self.listWinStart)
        self.selectedSong = self.music[self.listWinStart]
        self._populateMetadata(self.metaWin)
        while True:
            self._checkForInput()

    def stop(self):
        """
        Summary:
        -------
        stops the program itself
        """

        try:
            self.progressBarThread.kill()
        except Exception:
            pass
        try:
            self.queueThread.kill()
        except Exception:
            pass

        # Saves the latest settings
        writeConfigFile(self.configFile,
                        self.configuration)
        curses.nocbreak()
        self.stdscr.keypad(False)
        curses.echo()
        curses.endwin()
        sys.exit(0)

    def _populateSongs(self, win, songs, start=2):
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
        """

        x = 2
        y = 1
        for conf in self.configuration.keys():
            if conf.startswith("playlist_"):

                # The program checks if something is a song by splitting the file by "."
                # so the a "." is added at the end
                if not conf[9:].strip() + "." in self.music:
                    self.music.append(conf[9:].strip() + ".")
        try:
            for i, song in enumerate(songs[start:]):
                try:
                    songName = song[:-len(song.split(".")[-1]) - 1]
                    if i == 0:
                        songName = "]-> " + song[:-len(song.split(".")[-1]) - 1]
                    win.addstr(y, x, songName[:(self.stdscr.getmaxyx()[1] // 3 - 1)])
                except Exception:
                    continue
                self._refreshWindow(win)
                y += 1
        except Exception:
            self.music = [None]

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

        index = 0
        try:
            # Uses already selected song
            if not song:
                length = MP3(os.path.join(self.configuration["musicFolder"], self.selectedSong)).info.length

            # Uses given "song" parameter
            else:
                length = MP3(song).info.length
        except Exception:
            length = MP3(os.path.join(self.configuration["musicFolder"], self.selectedSong)).info.length

        self.barWin.addstr(2, 1, f"Progress", curses.color_pair(1))
        self._refreshWindow(self.barWin)
        while mixer.music.get_busy():
            # Don't do anything while the song is paused
            if self.paused:
                continue

            self._setProgressBar(int(index))
            self._refreshWindow(self.barWin)
            self.barWinProgress = index
            time.sleep(1)
            index += (self.barWin.getmaxyx()[1] - 5) / length
        self.paused = True

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
        self.barWin.addstr(1, len("Playing: ") + 1, os.path.basename(self.playingSong)[:50] if self.playingSong else "")

        if self.paused and mixer.music.get_busy():
            self.barWin.addstr(2, self.barWin.getmaxyx()[1] // 2 - len(f"Paused") // 2, f"Paused", curses.color_pair(1))

        self.barWin.addstr(2, 1, f"Progress", curses.color_pair(1))
        self.barWin.addstr(3, 1, "=" * progress)

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

    def _populateMetadata(self, win, promptingForFolder=False):
        """
        Summary:
        -------
        fills a window with the information on the currently selected song.

        Parameters:
        -------
        win : curses.window
            The window to put the information on

        promptingForFolder : bool
            Wether or not to write the current folder path.
            This is set to True when the user is changing the folder
        """

        win.clear()
        logo = """
             ; 
             ;;
             ;';.
             ;  ;;
   -++-      ;   ;;
| MusiCli |  ;    ;;
   -++-      ;   ;'
             ;  ' 
        ,;;;,; 
        ;;;;;;
        `;;;;'
"""
        for i, line in enumerate(logo.split("\n")):
            win.addstr(6 + i, win.getmaxyx()[1] - 30, line, curses.color_pair(1))

        # The song is a single song
        if not self.currentPlaylist:
            file = TinyTag.get(os.path.join(self.configuration["musicFolder"], os.path.basename(self.selectedSong)))

            # All these try except are really ugly
            # I should find a better way, but this works
            # as a temporary solution
            try:
                self._addMetadata(win, 1, 2, "Title:", file.title)
            except Exception:
                self._addMetadata(win, 1, 2, "Title:", self.selectedSong[:-4])
            try:
                self._addMetadata(win, 4, 2, "Artist:", file.artist)
            except Exception:
                self._addMetadata(win, 4, 2, "Artist:", "<Unknown>")
            try:
                self._addMetadata(win, 7, 2, "Track #n:", file.track + " / " + file.track_total)
            except Exception:
                self._addMetadata(win, 7, 2, "Track #n:", "1 / 1")
            try:
                self._addMetadata(win, 10, 2, "Album:", file.album)
            except Exception:
                self._addMetadata(win, 10, 2, "Album:", "<Unknown>")

        # The song is actually a playlist
        else:
            self._addMetadata(win, 1, 2, "Type:", "Playlist")
            self._addMetadata(win, 4, 2, "Title:", self.currentPlaylist)
            win.addstr(7, 2, "Songs:", curses.color_pair(1))
            i = 8
            try:
                for index, song in enumerate(self.configuration[f"playlist_{self.currentPlaylist}"]):
                    if index == 7:
                        break
                    win.addstr(i, 2, song[:-4])
                    i += 1
                self._refreshWindow(win)
            except Exception:
                pass

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

        if f"playlist_{self.selectedSong[:-1]}" in self.configuration.keys():
            self._makeErrorPopup(self.popupWin, "Recursion error", "Add to Playlist")
            return

        if os.path.join(self.configuration["musicFolder"], self.selectedSong) \
                in self.configuration[f"playlist_{playlist}"]:
            self._makeErrorPopup(self.popupWin, "Song already is in playlist", "Add to Playlist")
            self._refreshEverything()
            return

        self.popupWin.clear()
        self.popupWin.refresh()
        self.configuration[f"playlist_{playlist}"].append(
            os.path.join(self.configuration["musicFolder"], self.selectedSong))
        self._refreshEverything()

    def _removeFromPlaylist(self):
        """
        Summary:
        -------
        prompts the user to remove the currently selected song
        from a playlist
        """

        if f"playlist_{self.selectedSong[:-1]}" in self.configuration.keys():
            self.popupWin.clear()
            self.popupWin.border(']', '[', '=', '=', '+', '+', '+', '+')
            self.popupWin.refresh()
            self.popupWin.addstr(2, 2, "Remove from Playlist",
                                 curses.color_pair(1))
            self.popupWin.addstr(5, 2, "Remove Playlist? <Y/N>", curses.color_pair(2))
            if self.popupWin.getstr(6, 2, 1).decode().lower() == "y":
                del self.configuration[f"playlist_{self.selectedSong[:-1]}"]
                self.music.remove(self.selectedSong)
                self.listWinStart = 0
            self.popupWin.refresh()
            self.popupWin.clear()
            self._refreshEverything()
            return

        self.popupWin = curses.newwin(self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 2,
                                      self.stdscr.getmaxyx()[0] // 4, self.stdscr.getmaxyx()[1] // 4)
        playlist = self._createPrompt(self.popupWin, "Remove from Playlist", "Playlist: ")

        if not playlist:
            self._makeErrorPopup(self.popupWin, "No name", "Remove from Playlist")
            return

        if f"playlist_{playlist}" not in self.configuration.keys():
            self._makeErrorPopup(self.popupWin, "Playlist doesn't exist", "Remove from Playlist")
            return

        if os.path.join(self.configuration["musicFolder"], self.selectedSong) \
                not in self.configuration[f"playlist_{playlist}"]:
            self._makeErrorPopup(self.popupWin, "Song is not in playlist", "Remove from Playlist")
            return

        self.popupWin.clear()
        self.popupWin.refresh()
        self.configuration[f"playlist_{playlist}"].remove(
            os.path.join(self.configuration["musicFolder"], self.selectedSong))
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


def main(stdscr):
    p = Player(stdscr)
    try:
        p.start()
    except KeyboardInterrupt:
        p.stop()


if __name__ == '__main__':
    curses.wrapper(main)  #TODO ctrl-c does not exit gracefully
