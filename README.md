# FM26 Moneyball Scout

A Moneyball-style scouting tool for Football Manager 26. It reads player stats straight from the running game with one click, so there is no exporting or spreadsheet juggling. It then ranks players by role scores built from percentiles, using the role weightings from Fmplaya's FM24 Statistics Spreadsheet (see [Credits](#credits)).

The tool has two sections at the top: **My Club** and **World Scout**.

- **My Club** has four sub-tabs:
  - **Squad**: every player contracted to your club, including youth and reserves. Players out on loan are marked "On loan at X", and players on loan to you are included.
  - **Shortlist**: players you have starred.
  - **Compare**: compare up to 3 players drawn from your squad, your shortlist, or both, with radar, pizza and bar charts.
  - **Graphs**: the World Scout graphs, showing only your squad and/or shortlist players who have minutes, with an age filter.
- Your club is detected automatically from the save (the game's human-manager record). A "My club" picker in Squad lets you choose another club. That choice is remembered for the same save.
- **World Scout** has five tabs: Scout, Compare, All players, Graphs and Rank. Graphs can be filtered by league, club, minutes and age, combined with AND or OR. Custom graphs can also plot season totals (goals, assists, goals + assists, non-penalty goals, xG, xA, appearances).

Click the ☆ next to any player in World Scout (or "☆ Shortlist" in a player's profile) to add them to the shortlist. The shortlist is kept between sessions, stored by the game's player ID.

## Requirements

- Windows 10 or 11
- Football Manager 26 (built and checked on game version 26.3.2)
- Microsoft Edge (included with Windows) for the app window
- To run from source: Python 3.12 or newer. The reader uses only the standard library.

## How to use

1. Open FM26 and load your save.
2. Start the tool:
   - **Exe:** download `FM26 Moneyball.exe` from the Releases page (or build it, see below) and double-click it. No Python needed.
   - **From source:** double-click `Start FM26 Moneyball.bat`.

   The tool opens in its own app window (Microsoft Edge's app mode: no tabs or address bar, with a private profile separate from your browsing). Closing that window stops the reader. Opening the exe again while it runs just brings the window back. If Edge is missing, it falls back to a small control window plus your default browser.
3. Choose which stats to use:
   - All competitive games (the default)
   - League only
   - Domestic cups
   - Continental
   - Everything, including friendlies

   Then click "Load from game". The first load takes about 15 seconds. Later reloads take about 2 seconds.
4. After playing more matches in FM26, click "Reload from game" to refresh the data. Changing the Stats selector in the header reloads it automatically.

## Every player is listed

- Every player in the game is loaded (about 30,000), including players with no minutes or incomplete stats. Missing values show as "–", and those players sort to the bottom.
- Role scores and percentiles are measured against the "percentile pool": players with at least 300 minutes. You can change that number in Player search ("Percentile pool"). The "Minutes between" boxes in Player search are only a filter and are empty by default.
- Players with some minutes but fewer than the pool's minimum are still placed within the pool. They are shown faded as a small sample and rank after pool players.

## Building the exe

- Install PyInstaller: `python -m pip install pyinstaller`
- Run `Build exe.bat`. The exe is written to the `dist` folder.

## How it works

- `reader/server.py` runs a local web server on 127.0.0.1 only. Nothing leaves your computer.
- `reader/fm26.py` opens the `fm.exe` process read-only. It cannot change the game or your save. It finds every player object by its C++ class name (ACTUAL_PLAYER) and reads stats, contract, club and league.
- It also finds the human manager object (HUMAN_NON_PLAYER) to work out which club you manage.
- `reader/export.py` turns this into the column names the scoring page uses (the same names as an FM24 stats export).
- `FM26 Moneyball.html` is the whole interface: percentiles, role scores, tables and charts. It can also load an older FM .html export or a saved players .json.
- `reader/classes.py` lists the game's C++ class names, which helps when mapping new structures.

## Limits

- Early in a season, many players have no minutes yet, so they have no stats or role scores until they play.
- Some players have no stored market value. The game shows a placeholder for them, so they appear as "–".
- Personality, playing style and weight are not read yet, so they show "–".
- Reserve and B-team players (about 0.6%) show their parent club and its league.
- Distance covered is low for the game's pre-loaded history matches. Matches you play yourself are fine.
- The tool was built and checked on FM26 build 26.3.2 (engine build id 6A229F1E-1D8D3000). A game patch may move some fields. All memory offsets are constants at the top of `reader/fm26.py`, so a patch means updating them there.

## Troubleshooting

- **"Can't reach the reader"**: start the exe (or the .bat file) again; with the .bat, keep its console window open.
- **"FM26 isn't running"**: open the game, load a save, then click Load again.
- You can also open `FM26 Moneyball.html` directly from disk, as long as the reader is running.
- **Windows SmartScreen or antivirus warns about the exe**: it is unsigned and reads another program's memory (read-only), which some scanners flag. Choose More info > Run anyway, or run from source with the .bat instead.
- **Log file**: `%LOCALAPPDATA%\FM26 Moneyball\reader.log`

## Credits

- The role weightings, the role list and the default league weights come from the **FM24 Statistics Spreadsheet** by **Fmplaya**: [FM24 Statistics Spreadsheet (for those that love moneyball)](https://community.sports-interactive.com/forums/topic/580105-fm24-statistics-spreadsheet-for-those-that-love-moneyball/) on the Sports Interactive Community forums. Thank you, Fmplaya.
- The memory reader, the FM26 port and the interface were written for this project.

## License

FM26 Moneyball Scout is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE).

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

## Disclaimer

This is an unofficial fan project. It is not affiliated with, endorsed by or connected to Sports Interactive or SEGA. Football Manager is a trademark of Sports Interactive and SEGA. The tool only reads the game's memory on your own computer and never modifies the game or your save files.
