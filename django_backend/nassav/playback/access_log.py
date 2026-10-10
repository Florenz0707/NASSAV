"""Keep signed media capabilities out of Uvicorn access records."""

from logging import Filter


class PlaybackAccessFilter(Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2]
            if "/api/playback-sessions/" in path and (
                "/assets/" in path or "/manifest/" in path
            ):
                record.args = (*args[:2], path.split("?", 1)[0], *args[3:])
        return True
