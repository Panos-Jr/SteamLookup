# Steam Lookup
https://steamlookup.net (may be outdated, if credits aren't adequate)

https://github.com/Panos-Jr/website-steamlookup - website



**SteamLook/** - main source files for SteamLookup itself

**save_gd/**, and **save_gd_core/** - source files for save_gd (save 'google drive'), most of them are contained in the former, with the latter having the GUI code and extra
You'll find it is also called Save Sync (which is the name for the GUI version of **save_gd**), which SteamLookup advertises it as.

When applying a game to Save Sync, you'll find it applies a proxy dll called version.dll, which will handle cloud syncing after you quit a game, by launching save_gd (CLI) as a detached process, you can work
with Save Sync without use of version.dll if you wish, you'll have to remove the `version.dll` manually from game files.



Join our discord server: https://discord.gg/8nucvsnWh9

Chrome is required for Selenium, but is not a strict requirement if you're only interested in using it for Steamtools, or OpenSteamTool
