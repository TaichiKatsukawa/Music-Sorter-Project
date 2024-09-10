import os
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pprint import pprint
import argparse
import time
import inflect
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans


os.environ["SPOTIPY_CLIENT_ID"] = 'df6334f4c6004c77b835f2349a85a531'
os.environ["SPOTIPY_CLIENT_SECRET"] = 'ca70b39b0705437e91221e5c5dfccb4b'
os.environ["SPOTIPY_REDIRECT_URI"] = 'https://127.0.0.1:8080'


def main(username, include_from, include_instrumental):
    app_name = "SoundAster"
    app_short_name = "S/Ast"


    print("Getting Spotify API token... ", end="", flush=True)
    scope = 'user-library-read playlist-read-private playlist-modify-private user-follow-read'
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope, open_browser=False), retries=0, status_retries=0)

    if sp:
        print("Done")

        con = sqlite3.connect(':memory:')
        create_sql_tables(con)

        tracks = get_tracks(sp, include_from)
        insert_tracks_to_db(tracks, con)

        unique_tracks = get_unique_tracks(con)
        track_characteristics = get_track_characteristics(sp, unique_tracks)
        insert_track_characteristics_to_db(track_characteristics, con)

        sql_query = (
            """SELECT *
            FROM tracks
            ;"""
        )
        songs_audio_features = pd.read_sql(sql_query, con)

        # Values defined by what Spotify considers an instrumental song
        if include_instrumental:
            max_instrumentalness = 1
        else:
            max_instrumentalness = 0.5

        user_confirmation = False
        while user_confirmation == False:
            while True:
                try:
                    clusters = int(input('How many playlists to create? '))
                    if clusters <= 0:
                        raise ValueError('Please input a number greater than 0')
                    else:
                        break
                except:
                    print('Invalid input. Please input an integer')

            df = pd.DataFrame.from_dict(songs_audio_features)
            kmeans = KMeans(n_clusters=clusters)
            label = kmeans.fit_predict(df[['valence', 'energy']])
            unique_labels = pd.unique(label)

            #np.tolist() to convert numpy int to python int
            playlist = {label.tolist(): [] for label in unique_labels}

            for i in unique_labels:
                songs = df[(label == i) & (df['instrumentalness'] <= max_instrumentalness)]['uri'].to_list()
                playlist[i.tolist()].extend(songs)
                plt.scatter(
                    df[(label == i) & (df['instrumentalness'] <= max_instrumentalness)]['valence'], 
                    df[(label == i) & (df['instrumentalness'] <= max_instrumentalness)]['energy'], 
                    label=i, s=10
                    )

            print('Showing groupings...')    
            plt.legend()
            plt.show()

            while True:
                answer = input('Confirm results? (y/n/c) ').lower()
                if answer == 'y' or answer == 'yes':
                    user_confirmation = True
                    break
                elif answer == 'n' or answer == 'no':
                    break
                elif answer == 'c' or answer == 'cancel':
                    sys.exit(0)
                else:
                    print('Invalid input')


        # Create playlists in Spotify
        limit_step = 100
        for classification in playlist:
            new_playlist = sp.user_playlist_create(
                                username,
                                f"{app_short_name} - {classification+1}",
                                public=False,
                                description=f"Playlist created by {app_name}"
                                )
            new_playlist_id = new_playlist['uri']
            for i in range(0, len(playlist[classification]), limit_step):
                batch = playlist[classification][i : i+limit_step]
                sp.playlist_add_items(new_playlist_id, batch)
        print("Playlists created successfully")


        con.close()
    else:
        print(f"Can't get token for {username}")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Sorts music into moods.",
                                     epilog="You may include multiple include_from (e.g.: project.py -p -a to include songs from playlists AND albums).\n"
                                            "If no arguments are provided, non-instrumental songs from liked-songs, albums, playlists and followed artists will be included.\n"
                                            "Spotify's algorithm isn't perfect so bear with that.\n"
                                            " ",
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('username', help='Spotify username')
    parser.add_argument('-ls', '--liked-songs', action='store_true', help="Include songs from \"Liked Songs\"")
    parser.add_argument('-pl', '--playlists', action='store_true', help="Include songs from playlists in your library")
    parser.add_argument('-al', '--albums', action='store_true', help="Include songs from albums in your library")
    parser.add_argument('-ar', '--artists', action='store_true', help="Include all songs from followed artists")
    parser.add_argument('-ft', '--featured', action='store_true', help="Include all songs that followed artists feature on")
    parser.add_argument('-in', '--instrumental', action='store_true', help="Include instrumental music")
    args = parser.parse_args()
    # return username, include_from, instrumental
    return args.username, \
        {'liked_songs': args.liked_songs,
         'playlists': args.playlists,
         'albums': args.albums,
         'artists': args.artists,
         'featured': args.featured}, \
        args.instrumental


def get_tracks(sp: spotipy, include_from: dict) -> list:
    get = GetSongs(sp)
    tracks = []
    # Check if no flags were inputted
    if all([not x for x in include_from.values()]):
        tracks.extend(get.liked_songs())
        tracks.extend(get.playlists())
        tracks.extend(get.albums())
        tracks.extend(get.artists('album,single'))
    else:
        if include_from['liked_songs']:
            tracks.extend(get.liked_songs())
        if include_from['playlists']:
            tracks.extend(get.playlists())
        if include_from['albums']:
            tracks.extend(get.albums())
        if include_from['artists']:
            tracks.extend(get.artists('album,single'))
        if include_from['featured']:
            tracks.extend(get.artists('appears_on'))
    return tracks


class GetSongs:
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
            tracks.extend(item['track'] for item in response['items'])
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
                tracks.extend(item['track'] for item in self.sp.playlist_items(playlist['uri'], fields='items.track')['items'])
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
                tracks.extend(item for item in album['album']['tracks']['items'])
                time.sleep(1)
        print("Done")
        return tracks

    def artist_albums_tracks(self, artist_id, groups: str=None) -> list:
        artist = self.sp.artist(artist_id)['name']
        print(f"Getting {artist}'s tracks... ", end="", flush=True)
        tracks = []
        new_limit_step = 20 # To accomodate for sp.albums() 20 item limit
        for offset in range(0, self.max_api_calls, new_limit_step):
            response = self.sp.artist_albums(artist_id, include_groups=groups, limit=new_limit_step, offset=offset)
            if len(response) == 0:
                break
            albums_batch = [album['uri'] for album in response['items']]
            albums_tracks = [item['tracks']['items'] for item in self.sp.albums(albums_batch)['albums']]
            for track in albums_tracks:
                tracks.extend(track)
            time.sleep(1)
        print("Done")
        return tracks

    def artists(self, groups: str=None) -> list:
        inf = inflect.engine()
        album_types = inf.join([inf.plural(type) for type in groups.split(',')], final_sep="")
        print(f"Getting artists' {album_types}... ")

        tracks = []
        last_artist = None
        for offset in range(0, self.max_api_calls, self.limit_step):
            response = self.sp.current_user_followed_artists(limit=self.limit_step, after=last_artist)
            if len(response) == 0:
                break
            artists_batch = [item['uri'] for item in response['artists']['items']]
            if len(artists_batch) == 0:
                break
            last_artist = artists_batch[-1]
            for artist in artists_batch:
                batch = self.artist_albums_tracks(artist, groups)
                tracks.extend(batch)
                time.sleep(1)
        return tracks
    
def create_sql_tables(con: sqlite3):
    sql_statements = [
        """DROP TABLE IF EXISTS tracks;""",
        """DROP TABLE IF EXISTS artists;""",
        """DROP TABLE IF EXISTS track_artists""",

        """CREATE TABLE tracks (
            uri TEXT PRIMARY KEY,
            energy REAL,
            valence REAL,
            instrumentalness REAL,
            liked_song INTEGER CHECK (liked_song IN (0, 1)) DEFAULT 0
        );""",

        """CREATE TABLE artists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );""",

        """CREATE TABLE track_artists (
            track_uri TEXT REFERENCES tracks (id),
            artist_id TEXT REFERENCES artists (id)
        );"""
    ]

    try:
        cursor = con.cursor()
        for statement in sql_statements:
            cursor.execute(statement)
        con.commit()
    except sqlite3.Error as e:
        print(e)

def tracks_to_df(tracks: dict):
    metadata = ['uri', 'name']
    df = pd.json_normalize(tracks, record_path='artists', meta=metadata, record_prefix='artist_')
    df.drop_duplicates()
    df = df.rename(columns={'uri': 'track_uri'})
    return df[['track_uri', 'artist_id']]

def insert_tracks_to_db(tracks: dict, con: sqlite3) -> None:
    metadata = ['uri', 'name']
    df = pd.json_normalize(tracks, record_path='artists', meta=metadata, record_prefix='artist_')
    df.drop_duplicates()
    df = df.rename(columns={'uri': 'track_uri'})
    df[['track_uri', 'artist_id']].to_sql('track_artists', con=con, if_exists='append', index=False)

def get_unique_tracks(con: sqlite3) -> list:
    cursor = con.cursor()
    sql_query = (
        """SELECT DISTINCT track_uri
            FROM track_artists
        ;"""
    )
    cursor.execute(sql_query)
    return [row[0] for row in cursor]

def get_track_characteristics(sp: spotipy, unique_tracks: list, limit_step=100) -> list:
    track_characteristics = []
    for i in range(0, len(unique_tracks), limit_step):
        batch = unique_tracks[i : i+limit_step]
        track_characteristics.extend(sp.audio_features(batch))
    return track_characteristics

def insert_track_characteristics_to_db(track_characteristics: dict, con: sqlite3) -> None:
    df = pd.DataFrame.from_dict(track_characteristics)
    df[['uri', 'valence', 'energy', 'instrumentalness']].to_sql('tracks', con=con, if_exists='append', index=False)


if __name__ == '__main__':
    args = parse_arguments()
    main(*args)