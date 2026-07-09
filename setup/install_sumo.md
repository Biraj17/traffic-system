# Installing SUMO

SUMO (Simulation of Urban MObility) is the traffic simulation engine this
project runs on. It's a system-level install, not a pip package.

## macOS

```bash
brew install --cask sumo-gui
```

This installs SUMO into `/opt/homebrew` (Apple Silicon) or `/usr/local`
(Intel) and normally sets `SUMO_HOME` for you. If it doesn't, add to your
shell profile (`~/.zshrc`):

```bash
export SUMO_HOME=/opt/homebrew/opt/sumo/share/sumo   # adjust if using Intel Homebrew
export PATH="$SUMO_HOME/bin:$PATH"
```

Reload your shell (`source ~/.zshrc` or open a new terminal) after editing.

## Linux (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc
```

`SUMO_HOME` is usually set automatically to `/usr/share/sumo`. If not:

```bash
export SUMO_HOME=/usr/share/sumo
```

## Windows

Download the installer from https://sumo.dlr.de/docs/Downloads.php, run it,
and make sure "Add SUMO to PATH" is checked during setup. Reboot afterwards
so `SUMO_HOME` and `PATH` take effect.

## Verify the install

```bash
sumo --version
sumo-gui --version
echo $SUMO_HOME        # Windows: echo %SUMO_HOME%
```

All three should succeed before running `python setup/build_network.py`.
