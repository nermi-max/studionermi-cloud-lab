# StudioNermi Cloud Lab

A simple Python desktop application built with PySide6, featuring a dark interface.

- **Open File** opens a file picker and displays the selected filename. It does not edit or execute the file.
- **Settings** displays information about the theme; configurable preferences are not implemented yet.
- **Exit** closes the application.

## Run on Linux Mint

Requires Python 3.9 or newer and a graphical desktop session. From a terminal:

```bash
sudo apt update
sudo apt install python3 python3-venv libgl1 libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0
cd /path/to/studionermi-cloud-lab
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

For subsequent launches, enter the project directory, activate `.venv`, and run
`python main.py`. Do not run the application with sudo.

If Qt reports a missing `xcb` plugin dependency, confirm the system packages above
are installed. For a Wayland-specific issue, try `QT_QPA_PLATFORM=xcb python main.py`
from your desktop session.

## Tests in a cloud environment

After installing the requirements in the virtual environment:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

These tests create the real Qt window and exercise file selection, cancellation,
the Settings dialog, and Exit without a display server. The file picker result is
mocked; native desktop file picker integration and visual appearance should also
be checked manually on Linux Mint.
