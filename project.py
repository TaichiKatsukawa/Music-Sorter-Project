import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pprint import pprint
import argparse
import time
import inflect


os.environ["SPOTIPY_CLIENT_ID"] = 'df6334f4c6004c77b835f2349a85a531'
os.environ["SPOTIPY_CLIENT_SECRET"] = 'ca70b39b0705437e91221e5c5dfccb4b'
os.environ["SPOTIPY_REDIRECT_URI"] = 'https://127.0.0.1:8080'


def main(username, categories, include_instrumental):
    app_name = "SoundAsterism"
    app_short_name = "S/Ast"

    # username = 31alebydqedyhuo6jyg27ox3xcaq
    print("Getting Spotify API token... ", end="", flush=True)
    scope = 'user-library-read playlist-read-private playlist-modify-private user-follow-read'
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope, open_browser=False), retries=0, status_retries=0)

    if sp:
        print("Done")

        songs_uri = list(get_songs_uri(sp, categories))
        songs_audio_features = get_songs_audio_features(sp, songs_uri)

        avg_features = get_avg_features(songs_audio_features)
        avg_valence = avg_features['valence']
        avg_energy = avg_features['energy']

        # Values defined by what Spotify considers a instrumental song
        if include_instrumental:
            max_instrumentalness = 1
        else:
            max_instrumentalness = 0.5

        pl_classifications = ['LowV/LowE', 'LowV/HighE', 'HighV/LowE', 'HighV/HighE']
        pl = {classification: [] for classification in pl_classifications}

        # Classify songs
        for song in songs_audio_features:
            if song['instrumentalness'] <= max_instrumentalness:
                if song['valence'] < avg_valence:
                    if song['energy'] < avg_energy:
                        pl['LowV/LowE'].append(song['uri'])
                    else:
                        pl['LowV/HighE'].append(song['uri'])
                else:
                    if song['energy'] < avg_energy:
                        pl['HighV/LowE'].append(song['uri'])
                    else:
                        pl['HighV/HighE'].append(song['uri'])


        # Create playlists in Spotify
        limit_step = 100
        for classification in pl:
            sp.user_playlist_create(username,
                                    f"{app_short_name}_{classification}",
                                    public=False,
                                    description=f"Playlist created by {app_name}")
            playlists = sp.user_playlists(username)
            new_pl = list(playlists['items'])[0]['uri']
            for i in range(0, len(pl[classification]), limit_step):
                batch = pl[classification][i : i+limit_step]
                sp.playlist_add_items(new_pl, batch)
        print("Playlists created successfully")
    else:
        print(f"Can't get token for {username}")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Sorts music into moods.",
                                     epilog="You may include multiple categories (e.g.: project.py -p -a to include songs from playlists AND albums).\n"
                                            "If no arguments are provided, non-instrumental songs from liked-songs, albums, playlists and followed artists will be included.\n"
                                            "Spotify's algorithm isn't perfect so bear with that.\n"
                                            " ",
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('username', help='Spotify username')
    parser.add_argument('-ls', '--liked-songs', action='store_true', help="Include songs from \"Liked Songs\"")
    parser.add_argument('-pl', '--playlists', action='store_true', help="Include songs from albums in your library")
    parser.add_argument('-al', '--albums', action='store_true', help="Include songs from playlists in your library")
    parser.add_argument('-ar', '--artists', action='store_true', help="Include all songs from followed artists")
    parser.add_argument('-ft', '--featured', action='store_true', help="Include all songs that followed artists feature on")
    parser.add_argument('-in', '--instrumental', action='store_true', help="Include instrumental music")
    args = parser.parse_args()
    # return username, categories, instrumental
    return args.username, \
        {'include_liked_songs': args.liked_songs,
         'include_playlists': args.playlists,
         'include_albums': args.albums,
         'include_artists': args.artists,
         'include_featured': args.featured}, \
        args.instrumental


def get_songs_uri(sp: spotipy, categories: dict) -> set:
    songs_uri = set()
    get = Get_songs(sp)
    # Check if no flags were inputted
    if all([not x for x in categories.values()]):
        songs_uri.update(get.liked_songs())
        songs_uri.update(get.playlists())
        songs_uri.update(get.albums())
        songs_uri.update(get.artists('album,single'))
    else:
        if categories['include_liked_songs']:
            songs_uri.update(get.liked_songs())
        if categories['include_playlists']:
            songs_uri.update(get.playlists())
        if categories['include_albums']:
            songs_uri.update(get.albums())
        if categories['include_artists']:
            songs_uri.update(get.artists('album,single'))
        if categories['include_featured']:
            songs_uri.update(get.artists('appears_on'))
    return songs_uri


def get_songs_audio_features(sp: spotipy, songs_uri: list, limit_step=100) -> list:
    songs_audio_features = []
    for i in range(0, len(songs_uri), limit_step):
        batch = songs_uri[i : i+limit_step]
        songs_audio_features.extend(sp.audio_features(batch))
    return songs_audio_features


def get_avg_features(songs_audio_features: list) -> dict:
    total_valence = 0
    total_energy = 0
    song_count = 0
    for song in songs_audio_features:
        total_valence += song['valence']
        total_energy += song['energy']
        song_count += 1
    avg_valence = total_valence/song_count
    avg_energy = total_energy/song_count
    return {'valence': avg_valence, 'energy': avg_energy}


class Get_songs:
    def __init__(self, sp: spotipy, limit_step=50):
        self.sp = sp
        self.limit_step = limit_step
        self.max_api_calls = 5*limit_step

    def liked_songs(self) -> list:
        print("Getting Liked Songs... ", end="", flush=True)
        tracks = []
        for offset in range(0, self.max_api_calls, self.limit_step):
            response = self.sp.current_user_saved_tracks(limit=self.limit_step, offset=offset)
            if len(response) == 0:
                break
            tracks.extend(item['track']['uri'] for item in response['items'])
        print("Done")
        return tracks

    def playlists(self) -> list:
        print("Getting playlists... ", end="", flush=True)
        tracks = []
        for offset in range(0, self.max_api_calls, self.limit_step):
            response = self.sp.current_user_playlists(limit=self.limit_step, offset=offset)
            if len(response) == 0:
                break
            for playlist in response['items']:
                tracks.extend(item['track']['uri'] for item in self.sp.playlist_items(playlist['uri'], fields='items.track.uri')['items'])
                time.sleep(1)
        print("Done")
        return tracks

    def albums(self) -> list:
        print("Getting albums... ", end="", flush=True)
        tracks = []
        for offset in range(0, self.max_api_calls, self.limit_step):
            response = self.sp.current_user_saved_albums(limit=self.limit_step, offset=offset)
            if len(response) == 0:
                break
            for album in response['items']:
                tracks.extend(item['uri'] for item in album['album']['tracks']['items'])
                time.sleep(1)
        print("Done")
        return tracks

    def artist_albums_tracks(self, artist_id, album_type: str=None) -> list:
        artist = self.sp.artist(artist_id)['name']
        print(f"Getting {artist}'s tracks... ", end="", flush=True)
        tracks = []
        for offset in range(0, self.max_api_calls, self.limit_step):
            response = self.sp.artist_albums(artist_id, album_type=album_type, limit=self.limit_step, offset=offset)
            if len(response) == 0:
                break
            for album in response['items']:
                tracks.extend(item['uri'] for item in self.sp.album_tracks(album['uri'])['items'])
                time.sleep(1)
        print("Done")
        return tracks

    def artists(self, album_type: str=None) -> list:
        inf = inflect.engine()
        album_types = inf.join([inf.plural(type) for type in album_type.split(',')], final_sep="")
        print(f"Getting artists' {album_types}... ")

        tracks = []
        last_artist = None
        for offset in range(0, self.max_api_calls, self.limit_step):
            response = self.sp.current_user_followed_artists(limit=self.limit_step, after=last_artist)
            if len(response) == 0:
                break
            artists = [item['uri'] for item in response['artists']['items']]
            if len(artists) == 0:
                break
            last_artist = artists[-1]
            for artist in artists:
                tracks.extend(self.artist_albums_tracks(artist, album_type))
                time.sleep(1)
        return tracks


if __name__ == '__main__':
    args = parse_arguments()
    main(*args)
