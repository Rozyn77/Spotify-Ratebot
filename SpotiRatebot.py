import discord
from discord.ext import commands
import os
import random
import asyncio
import uuid # Do generowania unikalnych ID sesji piosenek
import datetime # Do timestampów dla debugowania

# --- KONFIGURACJA BOTA ---
# PAMIĘTAJ: Zastąp ten placeholder swoim rzeczywistym tokenem bota!
TOKEN = "TOKEN" 
COMMAND_PREFIX = '!'

# --- DEKLARACJA INTENCJI ---
intents = discord.Intents.default()
intents.members = True       
intents.presences = True     
intents.message_content = True

# --- INICJALIZACJA BOTA ---
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# --- KONFIGURACJA GRY (ZMIENNE GLOBALNE) ---
game_active = False          
registration_active = False  
registered_players = set()   
players = []                 
current_host_index = -1      
songs_played_this_round = 0  
max_songs_per_host = 0   
game_channel = None          
registration_message = None  

# Zmienne do śledzenia ostatnio wykrytej piosenki Spotify, niezależnie od pauz
_last_detected_spotify_track_id = None
_last_detected_spotify_track_title = None

# Zmienne specyficzne dla aktualnie odtwarzanej piosenki (sesji) w grze
current_session_song_id = None # Unikalny ID dla każdej "sesji" piosenki (np. 1 piosenka na raz)
message_to_update = None     # Wiadomość Discord z embedem piosenki do aktualizacji ocen
last_message_send_time = None # Timestamp ostatniego wysłania/edycji embeda piosenki

# Dane gry (przechowywane przez całą grę)
scores = {}                  # {session_song_id: {user_id: rating}}
song_details = {}            # {session_song_id: {'title': ..., 'artist': ..., 'host_id': ..., 'url': ..., 'album_cover_url': ...}}

# Nowe zmienne do zarządzania spamowaniem ocenami i dyskwalifikacją
user_rating_attempts = {}    # {session_song_id: {user_id: count}}
MAX_RATING_ATTEMPTS = 5      
disqualified_players = set() 

# Flaga do debugowania: czy host może oceniać własne piosenki
DEBUG_ALLOW_HOST_RATING = True # USTAWIONE NA TRUE DLA TESTÓW SOLO

# Reakcje, które będą używane do oceniania (emotikony od 0 do 10)
RATING_EMOJIS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# Emotikona do zgłaszania się do gry
JOIN_GAME_EMOJI = "✋"
MIN_PLAYERS_REQUIRED = 1 # Zmieniono na 1 dla łatwiejszego debugowania solo


# --- ZDARZENIA BOTA ---
@bot.event
async def on_ready():
    """Wywoływane, gdy bot połączy się z Discordem i jest gotowy do pracy."""
    print(f'Zalogowano jako {bot.user.name} ({bot.user.id})')
    print(f'Bot jest gotowy! Zaproś go na serwer używając linku (wymaga uprawnień administratora dla pełnej funkcjonalności):')
    print(f'https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands')
    print('---')

@bot.event
async def on_presence_update(before, after):
    """
    Wywoływane, gdy status lub aktywność użytkownika się zmienia.
    Służy do monitorowania statusu Spotify obecnego hosta.
    """
    global game_active, players, current_host_index, songs_played_this_round, \
           max_songs_per_host, game_channel, current_session_song_id, \
           last_message_send_time, _last_detected_spotify_track_id, _last_detected_spotify_track_title

    if not game_active or current_host_index == -1 or not game_channel:
        return

    # Upewnij się, że current_host_index jest prawidłowy
    if current_host_index >= len(players):
        print(f"Błąd: current_host_index ({current_host_index}) poza zakresem players ({len(players)}). Kończę grę.")
        await end_game(game_channel) 
        return

    current_host = players[current_host_index]

    if after.id != current_host.id:
        return

    spotify_activity = None
    for activity in after.activities:
        if isinstance(activity, discord.Spotify):
            spotify_activity = activity
            break

    # Jeśli host słucha Spotify
    if spotify_activity:
        await asyncio.sleep(2) # Daj Spotify czas na aktualizację
        
        refreshed_member = game_channel.guild.get_member(after.id)
        if not refreshed_member: return
        
        refreshed_spotify_activity = None
        for activity in refreshed_member.activities:
            if isinstance(activity, discord.Spotify):
                refreshed_spotify_activity = activity
                break
        
        if refreshed_spotify_activity:
            # Sprawdzamy, czy to naprawdę nowa piosenka (inny track_id)
            # LUB czy host zaczął słuchać po całkowitym braku aktywności (wtedy _last_detected_spotify_track_id jest None)
            # LUB (system awaryjny) track_id jest ten sam, ale tytuł się zmienił (bardzo rzadkie, ale możliwe)
            is_new_track = (
                refreshed_spotify_activity.track_id != _last_detected_spotify_track_id or
                (_last_detected_spotify_track_id is None and refreshed_spotify_activity.track_id is not None) or
                (refreshed_spotify_activity.track_id == _last_detected_spotify_track_id and refreshed_spotify_activity.title != _last_detected_spotify_track_title)
            )

            if is_new_track:
                # Sprawdzamy, czy host nie przekroczył limitu piosenek
                if songs_played_this_round < max_songs_per_host:
                    
                    # Aktualizujemy nasze "ostatnio wykryte" ID i tytuł
                    _last_detected_spotify_track_id = refreshed_spotify_activity.track_id
                    _last_detected_spotify_track_title = refreshed_spotify_activity.title
                    
                    # Dodatkowe zabezpieczenie: nie wysyłaj nowej wiadomości zbyt szybko po poprzedniej
                    if last_message_send_time is None or \
                       (datetime.datetime.now() - last_message_send_time).total_seconds() > 3: # min 3 sekundy odstępu
                        
                        songs_played_this_round += 1
                        last_message_send_time = datetime.datetime.now() # Zaktualizuj timestamp
                        await handle_new_song_detected(refreshed_spotify_activity)
                        # POPRAWIONA LITERÓWKA: "refrespaced_spotify_activity" zmienione na "refreshed_spotify_activity"
                        await game_channel.send(f"**{current_host.mention}** puścił: **{refreshed_spotify_activity.title}** by **{', '.join(refreshed_spotify_activity.artists)}**! Oceniajcie!")
                else:
                    await game_channel.send(f"{current_host.mention}, pokazałeś już {max_songs_per_host} piosenki w tej turze. Użyj `!next_song` aby przejść do następnego gracza.", delete_after=10)
            # else:
                # print(f"Host kontynuuje słuchanie tej samej piosenki: {refreshed_spotify_activity.title}. Ignoruję.")
    else: # Jeśli spotify_activity jest None (użytkownik przestał słuchać/spauzował)
        # WAŻNA ZMIANA: NIE resetujemy _last_detected_spotify_track_id ani _last_detected_spotify_track_title tutaj.
        # Te zmienne zachowują wartość ostatnio wykrytej piosenki,
        # co pozwala na prawidłowe odróżnienie wznowienia tej samej piosenki od nowej.
        pass # Brak akcji resetowania w tym bloku


@bot.event
async def on_reaction_add(reaction, user):
    """
    Wywoływane, gdy użytkownik doda reakcję do wiadomości. Obsługuje zgłoszenia do gry i zbieranie ocen.
    """
    global scores, song_details, message_to_update, players, \
           registration_active, registered_players, registration_message, JOIN_GAME_EMOJI, \
           user_rating_attempts, MAX_RATING_ATTEMPTS, disqualified_players, current_session_song_id, \
           DEBUG_ALLOW_HOST_RATING

    if user.bot:
        return

    # --- Obsługa zgłoszeń do gry ---
    if registration_active and registration_message and reaction.message.id == registration_message.id:
        if str(reaction.emoji) == JOIN_GAME_EMOJI:
            member = reaction.message.guild.get_member(user.id)
            if member and not member.bot and member.status != discord.Status.offline:
                if member not in registered_players:
                    registered_players.add(member)
                    print(f"{user.display_name} dołączył do gry.")
                else:
                    try:
                        await reaction.remove(user)
                    except (discord.Forbidden, discord.NotFound):
                        print(f"Brak uprawnień lub reakcja nie istnieje, aby ją usunąć od {user.display_name} (użytkownik już zgłoszony).")
            else:
                try:
                    await reaction.remove(user)
                except (discord.Forbidden, discord.NotFound):
                    print(f"Brak uprawnień lub reakcja nie istnieje, aby ją usunąć od {user.display_name} (offline/bot).")
        else:
            try:
                await reaction.remove(user)
            except (discord.Forbidden, discord.NotFound):
                print(f"Brak uprawnień lub reakcja nie istnieje, aby ją usunąć od {user.display_name} (nieprawidłowa emotka rejestracji).")
        return 

    # --- Obsługa oceniania piosenek ---
    if game_active and message_to_update and reaction.message.id == message_to_update.id and current_session_song_id:
        if current_host_index >= len(players):
            print(f"Błąd: current_host_index ({current_host_index}) poza zakresem players ({len(players)}). Nie mogę przetworzyć oceny.")
            try:
                await reaction.remove(user)
            except (discord.Forbidden, discord.NotFound):
                pass
            return

        is_current_host = (user.id == players[current_host_index].id)

        if user.id not in [p.id for p in players] or \
           (is_current_host and not DEBUG_ALLOW_HOST_RATING) or \
           user.id in disqualified_players:
            try:
                await reaction.remove(user) 
            except (discord.Forbidden, discord.NotFound):
                print(f"Brak uprawnień lub reakcja nie istnieje, aby ją usunąć od {user.display_name}")
            return

        emoji_str = str(reaction.emoji)
        
        if emoji_str in RATING_EMOJIS:
            rating_value = RATING_EMOJIS.index(emoji_str)
            
            if current_session_song_id not in user_rating_attempts:
                user_rating_attempts[current_session_song_id] = {}
            
            user_rating_attempts[current_session_song_id][user.id] = user_rating_attempts[current_session_song_id].get(user.id, 0) + 1

            if user_rating_attempts[current_session_song_id][user.id] > MAX_RATING_ATTEMPTS:
                if user.id not in disqualified_players:
                    disqualified_players.add(user.id)
                    if user in players:
                        players.remove(user) # Usuń z listy aktywnych graczy
                        await game_channel.send(f"**{user.mention}** został zdyskwalifikowany za zbyt częste próby oceniania na jednej piosence! Nie będzie mógł dalej brać udziału w grze.")
                        if is_current_host:
                            await game_channel.send(f"Ponieważ host ({user.mention}) został zdyskwalifikowany, przechodzimy do następnego gracza.")
                            await start_next_host_turn(game_channel)
                        if current_session_song_id in scores and user.id in scores[current_session_song_id]:
                            del scores[current_session_song_id][user.id]
                        await update_score_embed(message_to_update)
                    try:
                        await reaction.remove(user) 
                    except (discord.Forbidden, discord.NotFound):
                        pass
                    return 
            
            if current_session_song_id in scores and user.id in scores[current_session_song_id]:
                print(f"Gracz {user.display_name} już ocenił tę piosenkę. Ignoruję nową ocenę ({rating_value}).")
                try:
                    await reaction.remove(user) 
                except (discord.Forbidden, discord.NotFound):
                    print(f"Brak uprawnień lub reakcja nie istnieje, aby ją usunąć od {user.display_name}")
                return 

            scores[current_session_song_id][user.id] = rating_value
            print(f"Odebrano ocenę od {user.display_name}: {rating_value} dla piosenki {song_details[current_session_song_id]['title']}")
            
            # Po dodaniu oceny, usuń wszystkie inne reakcje oceniające tego użytkownika, aby była tylko jedna
            for r in reaction.message.reactions:
                if str(r.emoji) in RATING_EMOJIS and str(r.emoji) != emoji_str:
                    async for reactor in r.users():
                        if reactor.id == user.id:
                            try:
                                await r.remove(user)
                            # Obsługa błędu NotFound
                            except (discord.Forbidden, discord.NotFound) as e:
                                print(f"Nie udało się usunąć starej reakcji oceniającej od {user.display_name}. Powód: {type(e).__name__}")
                                pass 
            
            await update_score_embed(message_to_update)
        else:
            try:
                await reaction.remove(user)
            except (discord.Forbidden, discord.NotFound):
                print(f"Brak uprawnień lub reakcja nie istnieje, aby ją usunąć od {user.display_name}")

@bot.event
async def on_reaction_remove(reaction, user):
    """
    Wywoływane, gdy użytkownik usunie reakcję z wiadomości. Obsługuje wycofanie zgłoszenia do gry.
    """
    global registration_active, registered_players, registration_message, JOIN_GAME_EMOJI, disqualified_players

    if user.bot or user.id in disqualified_players:
        return

    # --- Obsługa wycofania zgłoszenia do gry ---
    if registration_active and registration_message and reaction.message.id == registration_message.id:
        if str(reaction.emoji) == JOIN_GAME_EMOJI:
            member = reaction.message.guild.get_member(user.id)
            if member and member in registered_players: 
                registered_players.remove(member)
                print(f"{user.display_name} wycofał się z gry.")
        return

    # --- Obsługa usuwania ocen piosenek ---
    # Usunięcie reakcji przez użytkownika celowo NIE USUNIE OCENY Z SYSTEMU, aby zapobiec manipulacji.
    if game_active and message_to_update and reaction.message.id == message_to_update.id:
        emoji_str = str(reaction.emoji)
        if emoji_str in RATING_EMOJIS:
            print(f"Gracz {user.display_name} usunął reakcję {emoji_str}. Ocena pozostaje w systemie.")


# --- KOMENDY BOTA ---
@bot.command(name='ping')
async def ping(ctx):
    """Prosta komenda testowa, sprawdza czy bot odpowiada."""
    await ctx.send(f'Pong! Latencja: {round(bot.latency * 1000)}ms')

@bot.command(name='start_game')
async def start_game_registration(ctx, num_songs_per_host: int = 3):
    """
    Rozpoczyna fazę rejestracji do gry Spotify Rating.
    """
    global game_active, registration_active, registered_players, players, \
           max_songs_per_host, game_channel, registration_message, MIN_PLAYERS_REQUIRED, \
           _last_detected_spotify_track_id, _last_detected_spotify_track_title, user_rating_attempts, disqualified_players, \
           scores, song_details, message_to_update, current_session_song_id, last_message_send_time

    if game_active or registration_active:
        await ctx.send("Gra jest już aktywna lub trwa rejestracja! Zakończ obecny proces komendą `!end_game`.")
        return

    if num_songs_per_host <= 0:
        await ctx.send("Liczba piosenek na hosta musi być większa niż 0.")
        return
    
    # Resetowanie wszystkich zmiennych stanu gry na start
    registration_active = True
    game_active = False 
    registered_players.clear()
    players.clear()           
    max_songs_per_host = num_songs_per_host
    game_channel = ctx.channel 
    _last_detected_spotify_track_id = None # Resetuj śledzenie piosenki na nową grę
    _last_detected_spotify_track_title = None # Resetuj śledzenie piosenki na nową grę
    user_rating_attempts.clear() 
    disqualified_players.clear() 
    scores.clear()               
    song_details.clear()         
    message_to_update = None     
    current_session_song_id = None
    last_message_send_time = None

    embed = discord.Embed(
        title="🎵 Rozpoczynamy Spotify Rating! 🎵",
        description=f"Gra się rozpocznie, gdy zgłosi się **minimum {MIN_PLAYERS_REQUIRED} graczy**.\n"
                    f"Każdy host zaprezentuje **{max_songs_per_host} piosenki**.\n\n"
                    f"**Aby dołączyć do gry, zareaguj na tę wiadomość emotikoną {JOIN_GAME_EMOJI}!**\n\n"
                    f"Rejestracja trwa do momentu użycia komendy `!end_registration` przez organizatora.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Pamiętaj, aby mieć aktywny status Spotify podczas swojej tury!")

    registration_message = await ctx.send(embed=embed)
    await registration_message.add_reaction(JOIN_GAME_EMOJI)


@bot.command(name='end_registration')
@commands.has_permissions(manage_channels=True)
async def end_registration(ctx):
    """
    Kończy fazę rejestracji i rozpoczyna grę z zarejestrowanymi graczami.
    """
    global registration_active, game_active, players, current_host_index, \
           songs_played_this_round, message_to_update, \
           registration_message, MIN_PLAYERS_REQUIRED, _last_detected_spotify_track_id, _last_detected_spotify_track_title, \
           user_rating_attempts, disqualified_players, current_session_song_id, last_message_send_time

    if not registration_active:
        await ctx.send("Rejestracja nie jest aktywna.")
        return

    # Pobierz aktualną listę reagujących
    if registration_message:
        try:
            # Użyj game_channel, ponieważ ctx może pochodzić z innego kanału
            registration_message = await game_channel.fetch_message(registration_message.id)
            react_users = set()
            for reaction in registration_message.reactions:
                if str(reaction.emoji) == JOIN_GAME_EMOJI:
                    async for user in reaction.users():
                        member = registration_message.guild.get_member(user.id)
                        if member and not member.bot and member.status != discord.Status.offline:
                            react_users.add(member)
            registered_players.update(react_users) # Użyj update zamiast przypisania, aby zachować istniejących graczy
        except discord.NotFound:
            await ctx.send("Wiadomość rejestracyjna nie została znaleziona. Spróbuj ponownie rozpocząć grę.")
            registration_active = False
            return
            
    if len(registered_players) < MIN_PLAYERS_REQUIRED:
        await ctx.send(f"Nie ma wystarczającej liczby zgłoszonych graczy. Potrzeba minimum {MIN_PLAYERS_REQUIRED}. Obecnie jest: {len(registered_players)}.")
        return

    registration_active = False 
    game_active = True         

    players = list(registered_players)
    players = [p for p in players if p.id not in disqualified_players]
    random.shuffle(players) 

    current_host_index = -1
    songs_played_this_round = 0
    message_to_update = None    
    _last_detected_spotify_track_id = None # Resetuj śledzenie piosenki na nową turę
    _last_detected_spotify_track_title = None # Resetuj śledzenie piosenki na nową turę
    current_session_song_id = None 
    last_message_send_time = None 

    if not players:
        await ctx.send("Wszyscy potencjalni gracze zostali zdyskwalifikowani lub nikt nie dołączył. Kończę grę.")
        await end_game(ctx)
        return

    players_mentions = [player.mention for player in players]
    await ctx.send(f"Rejestracja zakończona! Zarejestrowani gracze: {', '.join(players_mentions)}.")
    await ctx.send(f"Każdy gracz pokaże {max_songs_per_host} piosenki.")

    await start_next_host_turn(ctx)

@end_registration.error
async def end_registration_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Tylko osoby z uprawnieniami do zarządzania kanałami mogą zakończyć rejestrację.")

@bot.command(name='next_song')
async def next_song(ctx):
    """Przechodzi do następnej piosenki lub następnego hosta."""
    global game_active, songs_played_this_round, current_host_index, \
           max_songs_per_host, players, message_to_update, \
           user_rating_attempts, current_session_song_id, last_message_send_time, \
           _last_detected_spotify_track_id, _last_detected_spotify_track_title

    if not game_active:
        await ctx.send("Gra nie jest aktywna! Użyj `!start_game` aby rozpocząć.")
        return

    is_admin = ctx.author.guild_permissions.manage_channels
    if not (0 <= current_host_index < len(players) and players[current_host_index].id == ctx.author.id) and not is_admin:
        await ctx.send("Tylko obecny host lub administrator może przejść do następnej piosenki.")
        return

    if current_session_song_id and current_session_song_id in user_rating_attempts:
        del user_rating_attempts[current_session_song_id]

    if songs_played_this_round >= max_songs_per_host:
        await ctx.send(f"Obecny host ({players[current_host_index].mention}) pokazał już wszystkie swoje piosenki. Przechodzimy do następnego gracza!")
        
        if message_to_update:
            try:
                await message_to_update.delete()
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Błąd podczas usuwania poprzedniej wiadomości z embedem (koniec tury): {type(e).__name__}")
        
        await start_next_host_turn(ctx)
    else:
        await ctx.send("Przygotujcie się na kolejną piosenkę! Bot szuka aktywnego statusu Spotify.")
        
        if message_to_update:
            try:
                await message_to_update.delete()
            except (discord.NotFound, discord.Forbidden) as e:
                print(f"Błąd podczas usuwania poprzedniej wiadomości z embedem (następna piosenka): {type(e).__name__}")

        message_to_update = None    
        _last_detected_spotify_track_id = None # Resetuj, aby wykryć następną piosenkę tego samego hosta
        _last_detected_spotify_track_title = None # Resetuj, aby wykryć następną piosenkę tego samego hosta
        current_session_song_id = None
        last_message_send_time = None
        await ctx.send(f"**{players[current_host_index].mention}**, puść piosenkę na Spotify! Bot będzie ją monitorował.")

@bot.command(name='end_game')
async def end_game(ctx):
    """Zakończ aktualną grę i wyświetl wyniki."""
    global game_active, players, current_host_index, songs_played_this_round, \
           max_songs_per_host, scores, song_details, message_to_update, \
           game_channel, registration_active, registered_players, registration_message, \
           _last_detected_spotify_track_id, _last_detected_spotify_track_title, user_rating_attempts, disqualified_players, current_session_song_id, last_message_send_time

    if not game_active and not registration_active:
        await ctx.send("Nie ma aktywnej gry ani rejestracji do zakończenia.")
        return

    # KROK 1: Wyświetl wyniki, KIEDY DANE JESZCZE ISTNIEJĄ.
    await ctx.send("Gra została zakończona! Podliczam końcowe wyniki...")
    await display_final_scores(ctx)

    # KROK 2: Teraz, po wygenerowaniu rankingu, bezpiecznie zresetuj stan gry.
    if message_to_update:
        try:
            await message_to_update.delete()
        except (discord.NotFound, discord.Forbidden):
            print(f"Nie udało się usunąć wiadomości z embedem na koniec gry (mogła już nie istnieć).")
    
    # Czyszczenie wszystkich zmiennych stanu gry
    game_active = False
    registration_active = False
    registered_players.clear()
    players.clear()
    current_host_index = -1
    songs_played_this_round = 0
    _last_detected_spotify_track_id = None 
    _last_detected_spotify_track_title = None 
    current_session_song_id = None
    scores.clear()
    song_details.clear()
    message_to_update = None 
    game_channel = None
    registration_message = None
    user_rating_attempts.clear() 
    disqualified_players.clear() 
    last_message_send_time = None

# --- FUNKCJE POMOCNICZE ---

async def start_next_host_turn(ctx):
    """Pomocnicza funkcja do rozpoczęcia tury następnego hosta."""
    global current_host_index, players, songs_played_this_round, \
           message_to_update, _last_detected_spotify_track_id, _last_detected_spotify_track_title, user_rating_attempts, current_session_song_id, last_message_send_time

    # Upewnij się, że lista graczy jest aktualna
    players = [p for p in players if p.id not in disqualified_players]

    if not players:
        await ctx.send("Wszyscy gracze zostali zdyskwalifikowani lub opuścili grę. Kończę grę.")
        return

    current_host_index += 1
    if current_host_index >= len(players):
        await ctx.send("Wszyscy gracze pokazali swoje piosenki! Czas na ostateczne podsumowanie!")
        await end_game(ctx) 
        return

    # Reset stanu dla nowej tury
    songs_played_this_round = 0 
    message_to_update = None    
    _last_detected_spotify_track_id = None # Resetuj śledzenie piosenki na nową turę
    _last_detected_spotify_track_title = None # Resetuj śledzenie piosenki na nową turę
    current_session_song_id = None
    user_rating_attempts.clear() 
    last_message_send_time = None

    host = players[current_host_index]
    await ctx.send(f"**Teraz kolej na {host.mention}, aby pokazać swoje piosenki!**\nPuść swoją pierwszą piosenkę na Spotify! Bot będzie ją monitorował.")


async def handle_new_song_detected(spotify_activity):
    """Obsługuje wykrycie nowej piosenki Spotify."""
    global current_session_song_id, message_to_update, game_channel, scores, song_details, user_rating_attempts, last_message_send_time

    new_session_id = str(uuid.uuid4())
    current_session_song_id = new_session_id 

    host = players[current_host_index]

    song_details[current_session_song_id] = {
        'title': spotify_activity.title,
        'artist': ', '.join(spotify_activity.artists),
        'album': spotify_activity.album,
        'album_cover_url': spotify_activity.album_cover_url,
        'url': spotify_activity.track_url,
        'host_id': host.id,
    }
    scores[current_session_song_id] = {}
    user_rating_attempts[current_session_song_id] = {}

    embed = discord.Embed(
        title=f"🎧 Obecnie odtwarzana piosenka: {song_details[current_session_song_id]['title']}",
        description=f"**Artysta:** {song_details[current_session_song_id]['artist']}\n**Album:** {song_details[current_session_song_id]['album']}",
        color=discord.Color.green(),
        url=song_details[current_session_song_id]['url']
    )
    if song_details[current_session_song_id]['album_cover_url']:
        embed.set_thumbnail(url=song_details[current_session_song_id]['album_cover_url'])
    embed.add_field(name="Prowadzący", value=host.mention, inline=False)
    embed.add_field(name="Oceń piosenkę", value="Reaguj na tę wiadomość cyframi od 0 do 10 (np. 🔟).\n**Pierwsza ocena jest finalna!**", inline=False)
    embed.set_footer(text=f"Piosenka {songs_played_this_round} z {max_songs_per_host} dla {host.display_name}")

    message_to_update = await game_channel.send(embed=embed)
    print(f"Wysłano nowy embed piosenki o ID: {message_to_update.id}")
    
    # Dodawanie reakcji w tle, aby nie blokować reszty bota
    async def add_reactions():
        for emoji in RATING_EMOJIS:
            try:
                await message_to_update.add_reaction(emoji)
                await asyncio.sleep(0.3) # Krótsze opóźnienie
            except (discord.HTTPException, discord.NotFound) as e:
                print(f"Błąd podczas dodawania reakcji {emoji}: {type(e).__name__}")
                break # Przerwij, jeśli wiadomość została usunięta lub wystąpił inny błąd
    
    asyncio.create_task(add_reactions())
    last_message_send_time = datetime.datetime.now() 


async def update_score_embed(message):
    """Aktualizuje embed wiadomości z ocenami w czasie rzeczywistym."""
    global scores, song_details, current_session_song_id, players, current_host_index, disqualified_players

    if not current_session_song_id or not message:
        return

    try:
        current_song_scores = scores.get(current_session_song_id, {})
        current_song_info = song_details.get(current_session_song_id)

        if not current_song_info:
            print(f"Błąd: Nie znaleziono informacji o piosence dla ID sesji: {current_session_song_id}")
            return

        embed = message.embeds[0]
        
        # Obliczanie średniej
        average_rating = sum(current_song_scores.values()) / len(current_song_scores) if current_song_scores else 0

        # Tworzenie listy ocen
        ratings_text = "Brak ocen."
        if current_song_scores:
            sorted_ratings = sorted(current_song_scores.items(), key=lambda item: item[1], reverse=True)
            rated_users_info = []
            for user_id, rating in sorted_ratings:
                user = message.guild.get_member(user_id)
                rated_users_info.append(f"{user.display_name if user else f'ID: {user_id}'}: **{rating}**")
            ratings_text = "\n".join(rated_users_info)

        # Ustalanie liczby uprawnionych do głosowania
        if DEBUG_ALLOW_HOST_RATING:
            num_eligible_raters = len([p for p in players if p.id not in disqualified_players])
        else:
            host_id = players[current_host_index].id
            num_eligible_raters = len([p for p in players if p.id != host_id and p.id not in disqualified_players])
        
        # Aktualizacja pól embeda
        embed.set_field_at(1, name=f"Aktualne oceny ({len(current_song_scores)}/{num_eligible_raters}):", value=ratings_text, inline=False)
        # Dodajemy pole średniej, jeśli go nie ma, lub aktualizujemy istniejące
        if len(embed.fields) > 2 and "Średnia ocena" in embed.fields[2].name:
             embed.set_field_at(2, name="Średnia ocena:", value=f"**{average_rating:.2f}** / 10", inline=False)
        else:
            # Usuń stare pola ocen, jeśli istnieją, zanim dodamy nowe.
            while len(embed.fields) > 2:
                embed.remove_field(2)
            embed.add_field(name="Średnia ocena:", value=f"**{average_rating:.2f}** / 10", inline=False)

        await message.edit(embed=embed)

    except discord.NotFound:
        print(f"Nie udało się edytować wiadomości {message.id}: Wiadomość nie znaleziona.")
    except IndexError:
        print(f"Błąd podczas aktualizacji embeda: brak embeda w wiadomości lub nieprawidłowa struktura pól.")
    except Exception as e:
        print(f"Nieoczekiwany błąd podczas edycji embeda: {e}")


async def display_final_scores(ctx):
    """Wyświetla końcowy leaderboard."""
    # Używamy kopii, aby nie modyfikować globalnych zmiennych, które zaraz zostaną wyczyszczone
    final_scores = scores.copy()
    final_song_details = song_details.copy()
    final_registered_players = registered_players.copy()
    final_disqualified_players = disqualified_players.copy()

    if not final_song_details or not final_scores:
        await ctx.send("Nie zebrano żadnych ocenionych piosenek, aby wygenerować wyniki.")
        return

    eligible_presenters = {p.id: {'total_score': 0, 'song_count': 0, 'member': p} 
                           for p in final_registered_players if p.id not in final_disqualified_players}

    for session_id, song_info in final_song_details.items():
        host_id = song_info.get('host_id') 
        song_ratings = final_scores.get(session_id, {}) 

        if song_ratings and host_id in eligible_presenters:
            avg_rating = sum(song_ratings.values()) / len(song_ratings)
            eligible_presenters[host_id]['total_score'] += avg_rating
            eligible_presenters[host_id]['song_count'] += 1

    final_player_results = []
    for player_id, data in eligible_presenters.items():
        if data['song_count'] > 0:
            avg_player_score = data['total_score'] / data['song_count']
            final_player_results.append({'player': data['member'], 'average_score': avg_player_score, 'song_count': data['song_count']})
        else:
            final_player_results.append({'player': data['member'], 'average_score': 0, 'song_count': 0})

    final_player_results.sort(key=lambda x: x['average_score'], reverse=True)

    embed = discord.Embed(
        title="🏆 Końcowe Wyniki Gry Spotify Rating! 🏆",
        description="Ranking graczy na podstawie średniej ocen ich piosenek:",
        color=discord.Color.gold()
    )

    if not any(result['song_count'] > 0 for result in final_player_results):
        embed.description = "Brak wyników do wyświetlenia. Upewnij się, że host miał aktywny status Spotify i piosenki były oceniane."
    else:
        for i, result in enumerate(final_player_results):
            player = result['player']
            avg_score = result['average_score']
            song_count = result['song_count']
            status_text = " (ZDYSKWALIFIKOWANY)" if player.id in final_disqualified_players else ""
          
            embed.add_field(
                name=f"#{i+1}. {player.display_name}{status_text}",
                value=f"Średnia ocena: **{avg_score:.2f}** / 10 (z {song_count} piosenek)",
                inline=False
            )
    
    # Sekcja dla najwyżej ocenionych piosenek
    all_song_avg_ratings = []
    for session_id, s_details in final_song_details.items():
        song_ratings = final_scores.get(session_id, {})
        if song_ratings: 
            avg_rating = sum(song_ratings.values()) / len(song_ratings)
            all_song_avg_ratings.append({'info': s_details, 'avg': avg_rating})

    if all_song_avg_ratings:
        sorted_songs = sorted(all_song_avg_ratings, key=lambda x: x['avg'], reverse=True)
        song_leaderboard_text = []
        for i, song_data in enumerate(sorted_songs[:5]):
            song_info = song_data['info']
            avg_rating = song_data['avg']
            song_leaderboard_text.append(f"**{i+1}.** {song_info['title']} - {song_info['artist']} (**{avg_rating:.2f}**/10)")
        
        if song_leaderboard_text:
            embed.add_field(name="\n--- Najwyżej ocenione piosenki ---", value="\n".join(song_leaderboard_text), inline=False)

    await ctx.send(embed=embed)


# --- URUCHAMIANIE BOTA ---
if __name__ == '__main__':
    if TOKEN == "TOKEN" or not TOKEN:
        print("\nBŁĄD: Proszę wkleić swój rzeczywisty token bota w linii 'TOKEN ='.")
        print("Token znajdziesz w Discord Developer Portal, w zakładce 'Bot'.")
        print("Nie uruchamiam bota bez prawidłowego tokena.\n")
    else:
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            print("\nBŁĄD: Niepoprawny token bota. Sprawdź, czy skopiowałeś go prawidłowo.")
            print("Upewnij się również, że wszystkie wymagane 'Intents' są włączone w Discord Developer Portal (szczególnie 'Presence Intent' i 'Server Members Intent').")
        except Exception as e:
            print(f"\nWystąpił nieoczekiwany błąd podczas uruchamiania bota: {e}")