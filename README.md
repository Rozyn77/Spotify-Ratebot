# Discord Music Rating Bot

This Discord bot automates and manages a song rating game. Instead of relying on external APIs, it cleverly monitors user activity on Discord to automatically detect the currently playing Spotify track, then allows other players to rate it using emojis.

---
# **⚠This bot is currently only available in Polish and contains potential visual glitches/delays.⚠**

### Key Features

* **Automated Song Detection:** The bot identifies and displays song details (title, artist, album art) from an active user's Spotify status.
* **Emoji-Based Rating System:** Participants can rate songs on a scale from 0️⃣ to 🔟 using emoji reactions.
* **Scorekeeping & Leaderboard:** The bot calculates average ratings for each song and compiles a final leaderboard for all participants, as well as a list of the highest-rated songs.
* **Spam Prevention:** The bot includes a system to prevent rating spam, with a mechanism to disqualify repeat offenders.
* **Game Flow Automation:** It manages the entire game process, from player registration and song submission to the final score tally.
* **The currently playing song link** The embed message contains a clickable title directly to the song on Spotify.
* **⚠This bot does NOT support playing the songs itself!⚠** To properly play the game you need to use Spotify's synchronised listening jam or other methods like manualy playing it (it's best for all players to listen to the same audio in sync)
---

### Quick Start

#### Prerequisites
* Python 3.8+
* The `discord.py` library (version 2.x)

#### Installation & Setup
1.  Clone the repository:
    ```bash
    git clone https://github.com/Rozyn77/Spotify-Ratebot.git
    cd Spotify-Ratebot
    ```
2.  Install the required libraries:
    ```bash
    pip install discord.py
    ```
3.  Replace the placeholder `TOKEN` in `main.py` with your actual bot token.
4.  Run the bot:
    ```bash
    python main.py
    ```

---

### In-Game Commands

* `!start_game [number_of_songs]` - Starts the game registration. Players can join by reacting with an ✋ emoji.
* `!end_registration` - Ends the registration and begins the game.
* `!next_song` - Allows the current host or an administrator to move on to the next song.
* `!end_game` - Immediately ends the game and displays the final rankings.

### Plans for the future
* **Overall fixes to avoid embed message duplication and delays**
* **Off-game useful commands**
* **Visual improvements** like functional buttons for rating the song and or features like sending direct spotify link etc.
* **Actualy hosting the bot and making it available without the need for seting it up yourself**
* **Switching from outdated "!" prefix to the current "/" Discord command integration**
