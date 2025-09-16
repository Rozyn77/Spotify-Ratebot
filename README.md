Discord Music Rating Bot

This Discord bot automates and manages a song rating game. Instead of relying on external APIs, it cleverly monitors user activity on Discord to automatically detect the currently playing Spotify track, then allows other players to rate it using emojis.

Features

    Automated Song Detection: The bot identifies and displays song details (title, artist, album art) directly from a user's active Spotify status on Discord.

    Emoji-Based Rating System: Participants can rate songs on a scale from 0 to 10 using emoji reactions.

    Scorekeeping & Leaderboard: The bot calculates average ratings for each song and compiles a final leaderboard for all participants, as well as a list of the highest-rated songs.

    Game Flow Automation: It manages the entire game process, from player registration and song submission to the final score tally.

    Spam Prevention: The bot includes a system to prevent spamming of ratings, with a mechanism to disqualify repeat offenders.

How to Use

Prerequisites

    Python 3.8+

    The discord.py library (version 2.x)

Installation

    Clone the repository:
    Bash

git clone https://github.com/YourUsername/your-repository-name.git
cd your-repository-name

Install the required libraries:
Bash

pip install discord.py

Replace the placeholder TOKEN in main.py with your actual bot token from the Discord Developer Portal. For security, it's highly recommended to use environment variables to store your token.

Run the bot:
Bash

    python main.py

Bot Commands

    !start_game [number_of_songs_per_host] - Starts the game registration phase. Players can join by reacting with a specified emoji.

    !end_registration - Ends the registration and begins the game with the registered players.

    !next_song - Allows the current host or an administrator to move on to the next song in the round.

    !end_game - Immediately ends the current game and displays the final results.
