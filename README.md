# StudioNermi Cloud Lab 3.0

A Python and PySide6 desktop workspace with a clean dark interface, large controls,
and three resizable panels. Local browsing works without a key. The cloud assistant requires an OpenAI API account,
an API key, internet access, and available API credits.

- **Open Project** selects a local folder. The Project Explorer shows its files
  and folders, including hidden entries. Expand folders and select a file to preview it.
- **Code Preview** is read-only, with Python syntax highlighting, including
  multiline strings. UTF-8 text files up to 1 MiB are supported. Binary, oversized,
  missing, or unreadable files display an explanatory message.
- **Open File** retains the original standalone file picker and now previews the
  selected file as well as displaying its name and full path in a tooltip.
- **AI Assistant** answers programming questions and helps plan software projects
  through the official OpenAI Python SDK. Send or Enter submits your message;
  responses appear as selectable plain text, including suggested code.
  Requests run in a background thread so the desktop stays responsive.
- **Stop** cancels the local in-flight request and discards its response. It cannot
  guarantee cancellation of server-side processing or charges. Exit also cancels
  an active request before closing safely.
- **Settings** configures a masked API key and model (default `gpt-4.1-mini`).
  Keys can stay in memory for the current session or be saved explicitly to the
  secure system keyring. Model selection is session-only.
- **Exit** closes the application.

Opening a project or file never imports or executes project code. Files cannot be
edited, renamed, or deleted through the explorer or preview. The app does not
restore a previous project or execute anything at startup.

## Run on Linux Mint

Requires Python 3.10 or newer and a graphical desktop session. From a terminal:

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

## OpenAI API setup and costs

**ChatGPT Plus does not automatically include OpenAI API credits.** API usage has
separate billing. Create or sign in to an account at
[OpenAI Platform](https://platform.openai.com/), set up API billing/credits, and
create a project API key in [API keys](https://platform.openai.com/api-keys).
Check [current pricing](https://openai.com/api/pricing/) before use. Costs depend
on the model, input tokens, and output tokens; conversation history is resent
with each successful follow-up. Each response is capped at 2,048 output tokens.
Set appropriate project usage limits and monitor your usage in the Platform.

Choose one key configuration method:

1. Set `OPENAI_API_KEY` in the environment used to launch the app. To enter it
   without placing the key in shell command history, use Bash:

   ```bash
   read -rsp "OpenAI API key: " OPENAI_API_KEY
   echo
   export OPENAI_API_KEY
   python main.py
   unset OPENAI_API_KEY
   ```

   This applies to that terminal session; a MATE launcher will need its own
   environment or a Settings/keyring key. Never put keys in this repository.
2. Open **Settings**, enter a key in the password field, and Save. By default it
   stays only in process memory until the app exits. Cancel leaves it unchanged.
3. Optionally select **Save in system keyring**. The app accepts only Python
   keyring's Linux Secret Service backend, commonly provided by GNOME Keyring on
   Mint MATE. A working D-Bus session and an unlocked login keyring are needed.
   On Mint, install `gnome-keyring` and optionally `seahorse` through the system
   package manager. If unavailable or locked, saving reports an error; there is
   no plaintext fallback. Uncheck storage to use a session key instead. The
   `keyring` Python package is included for convenience but can be omitted when
   using only environment or session keys.

Key priority is **environment → session → system keyring**. Existing keys are
never displayed in Settings. **Forget session and saved key** clears the session
and attempts to delete the stored key; it reports failure if the keyring cannot
be accessed. It cannot remove an environment variable. If you replace a saved
key with a session-only key, the older saved key remains until explicitly removed.
The app does not hardcode, log, or write keys to configuration files. SDK/HTTP
logging is suppressed, and raw exception details are never shown.

If authentication fails, replace or check the key. For usage-limit errors, check
API billing, credits, and rate limits; a paid ChatGPT subscription does not fix
API quota. Connection/timeout errors suggest checking connectivity and retrying.
Model/access errors may require a different model name in Settings or API project
permissions. Requests time out after 60 seconds and are not automatically retried.

## Privacy and behavior

Only typed messages, successful conversation history, and a fixed assistant
instruction are sent to `https://api.openai.com/v1`. Selected project files are
**never uploaded automatically**. Paste only code or information you intend to
send to OpenAI. The assistant cannot read your explorer, run commands, or modify
files; generated code is text for you to review and copy manually. No tools or
code-execution features are enabled. Conversation history lives in memory and
is cleared on exit; OpenAI processes submitted content under its API policies.
Failed and stopped turns are displayed but excluded from future request history.
Long conversations can reach model context limits; restart the app to clear them.

## Automated tests

After installing requirements and activating the virtual environment:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Tests instantiate real Qt widgets and mock the OpenAI SDK and keyring. They use
no real credentials, network requests, or paid API calls. Coverage includes the
existing explorer/preview/highlighting features, SDK arguments and follow-up
history, responsive waiting, Stop, closing during requests, safe error messages,
missing keys, credential priority, secure storage failure, masked Settings,
and Exit. Native file picker and Secret Service integration should also be
checked in a real Linux Mint MATE desktop session.
