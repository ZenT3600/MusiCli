import os
import re
import ast
import string
import curses

from typing import Dict


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
