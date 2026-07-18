# mac-macro

A macOS app with a dark neon-style GUI and an on/off switch.

When the switch is **On**, press **F** to run:

1. Press `2`
2. Left click
3. Press `q`
4. Left click

## Install on your Mac

You need **macOS** and **Python 3**. Check that Python is installed by opening
Terminal and running:

```bash
python3 --version
```

Then download and set up the app:

```bash
git clone https://github.com/UNBLOCKERONLY/Minecraft-chud-macro.git
cd Minecraft-chud-macro
git switch cursor/mac-macro-app
chmod +x run.sh Launch.command
./run.sh
```

The first launch creates a private Python environment and installs the required
packages automatically. Future launches can be started by double-clicking
`Launch.command` in Finder.

If you do not have Git, open the repository on GitHub, select
**Code → Download ZIP**, unzip it, open the folder in Terminal, and run:

```bash
chmod +x run.sh Launch.command
./run.sh
```

If macOS blocks `Launch.command`, Control-click it in Finder, choose **Open**,
then confirm **Open**.

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## macOS permission (required)

This app needs **Accessibility** access so it can send keys and clicks:

1. Open **System Settings → Privacy & Security → Accessibility**
2. Click **+** and add **Terminal** (or whatever app you launch from)
3. Turn the toggle **On**
4. Quit and relaunch the app

## How to use

1. Launch the app
2. Flip the switch **On** (status becomes “Armed”)
3. Press **F** anywhere to fire the combo
4. Flip the switch **Off** when you’re done
