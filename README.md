# mac-macro

A macOS app with a dark neon-style GUI and an on/off switch.

When the switch is **On**, press **F** to run:

1. Press `2`
2. Left click
3. Press `q`
4. Left click

## Run

```bash
cd ~/mac-macro
./run.sh
```

Or manually:

```bash
cd ~/mac-macro
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
