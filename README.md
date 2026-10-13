# Steam Lookup
https://steamlookup.net (may be outdated, if credits aren't adequate)

https://github.com/Panos-Jr/website-steamlookup - website

Join our discord server: https://discord.gg/8nucvsnWh9

Chrome is required for Selenium, but is not a strict requirement if you're only interested in using it for Steamtools, or OpenSteamTool

If you plan on using the tool to help with SteamTools, or OpenSteamTool, make sure to obtain a Hubcap API key,
from here: https://hubcapmanifest.com/api-keys/stats

## Background
**SteamLook/** - main source files for SteamLookup itself

**save_gd/**, and **save_gd_core/** - source files for save_gd (save 'google drive'), most of them are contained in the former, with the latter having the GUI code and extra
You'll find it is also called Save Sync (which is the name for the GUI version of **save_gd**), which SteamLookup advertises it as.

When applying a game to Save Sync, you'll find it applies a proxy dll called version.dll, which will handle cloud syncing after you quit a game, by launching save_gd (CLI) as a detached process. You can work
with Save Sync without use of version.dll if you wish, you'll have to remove the `version.dll` manually from game files.

**OST Bypass** - Applies proxy dll  `dwmapi.dll` with the handler `steam_handler.exe` where when the game is launched, steam_handler will be launched as a detached process, and disable OST (by renaming OpenSteamTool.dll), but by first shutting down steam, and disabling the proxy to avoid an unnecessary repeat. When a game exits, it'll re-enable OST, and shutdown then start steam again.

In all instances that steam is launched using **OST Bypass** it is done so silently
