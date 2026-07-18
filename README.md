# Solar Macros

A macOS macro suite with a dark sidebar UI: Crystal, Sword, Mace, Cart, and UHC
tabs plus tools and app settings.

The **Mace** tab has the Key Click Combo macro. Flip its switch **On**, then
press **F** to run:

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
chmod +x run.sh "Solar Macros.command"
./run.sh
```

The first launch creates a private Python environment and installs the required
packages automatically. Future launches can be started by double-clicking
`Solar Macros.command` in Finder.

If you do not have Git, open the repository on GitHub, select
**Code → Download ZIP**, unzip it, open the folder in Terminal, and run:

```bash
chmod +x run.sh "Solar Macros.command"
./run.sh
```

If macOS blocks `Solar Macros.command`, Control-click it in Finder, choose
**Open**, then confirm **Open**.

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
2. Open the **Mace** tab
3. Flip the switch **On** (status becomes "Armed")
4. Press **F** anywhere to fire the combo
5. Flip the switch **Off** when you're done
