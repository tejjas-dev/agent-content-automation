from . import TypeSpec

SPEC = TypeSpec(
    name="drama",
    channels_env="DRAMA_POST_CHANNEL_IDS",
    fields=(("title", "📺 TITLE"), ("audio", "🎙 AUDIO"),
            ("episodes", "📺 EPISODES"), ("genre", "🎭 GENRE")),
    labels={
        "audio": r"audio|languages?",
        "episodes": r"total episodes?|episodes?|no\.? of episodes?",
        "genre": r"genres?|categories|category",
    },
    noise=("download", "720p", "480p", "1080p", "web-dl", "webrip", "hindi dubbed",
           "hindi dub", "dual audio", "full series", "all episodes", "watch online"),
)
