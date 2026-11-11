# StudioNermi Cloud Lab 2.0

A Python and PySide6 desktop workspace with a clean dark interface, large controls,
and three resizable panels. No API keys or cloud account are required.

- **Open Project** selects a local folder. The Project Explorer shows its files
  and folders, including hidden entries. Expand folders and select a file to preview it.
- **Code Preview** is read-only, with Python syntax highlighting, including
  multiline strings. UTF-8 text files up to 1 MiB are supported. Binary, oversized,
  missing, or unreadable files display an explanatory message.
- **Open File** retains the original standalone file picker and now previews the
  selected file as well as displaying its name and full path in a tooltip.
- **AI Assistant** accepts a message with Send or Enter and displays an explicit
  offline response. **The assistant is not yet connected to a cloud service.**
  Messages and project contents are never sent anywhere. Conversation text stays
  in memory only and disappears when the app closes.
- **Settings** displays the current dark appearance, read-only behavior, and
  offline assistant status. There are no configurable preferences yet.
- **Exit** closes the application.

Opening a project or file never imports or executes project code. Files cannot be
edited, renamed, or deleted through the explorer or preview. The app does not
restore a previous project or execute anything at startup.

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

For subsequent launches, activate `.venv` in the project directory and run
`python main.py`. Do not run the application with sudo. Recommended desktop
resolution: 1440 × 900 or larger; minimum window size: 960 × 640.

If Qt reports a missing `xcb` dependency, confirm the system packages above are
installed. For a Wayland issue, try `QT_QPA_PLATFORM=xcb python main.py` from your
desktop session.

## Automated tests

After installing requirements and activating the virtual environment:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Tests instantiate real Qt widgets and cover project selection, nested folders,
file selection and preview without executing code, cancellation, read-only
controls, Python highlighting and multiline strings, switching to plain text,
file errors and limits, offline assistant interactions, Settings, and Exit.
Only native picker results are mocked. No additional test dependencies are needed.
Native file picker integration and desktop appearance should also be checked on
Linux Mint.
