from Tribler.Core.dispersy.message import Packet
from Tribler.Core.dispersy.payload import Payload

class ChannelPayload(Payload):
    class Implementation(Payload.Implementation):
        def __init__(self, meta, name, description):
            assert isinstance(name, unicode)
            assert len(name) < 256
            assert isinstance(description, unicode)
            assert len(description) < 1024
            super(ChannelPayload.Implementation, self).__init__(meta)
            self._name = name
            self._description = description

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

class TorrentPayload(Payload):
    class Implementation(Payload.Implementation):
        def __init__(self, meta, infohash, timestamp):
            assert isinstance(infohash, str), 'infohash is a %s'%type(infohash)
            assert len(infohash) == 20, 'infohash has length %d'%len(infohash)
            assert isinstance(timestamp, (int, long))
            super(TorrentPayload.Implementation, self).__init__(meta)
            self._infohash = infohash
            self._timestamp = timestamp

        @property
        def infohash(self):
            return self._infohash

        @property
        def timestamp(self):
            return self._timestamp

class PlaylistPayload(Payload):
    class Implementation(Payload.Implementation):
        def __init__(self, meta, name, description):
            assert isinstance(name, unicode)
            assert len(name) < 255
            assert isinstance(description, unicode)
            assert len(description) < 1024
            super(PlaylistPayload.Implementation, self).__init__(meta)
            self._name = name
            self._description = description

        @property
        def name(self):
            return self._name

        @property
        def description(self):
            return self._description

class CommentPayload(Payload):
    class Implementation(Payload.Implementation):
        def __init__(self, meta, text, timestamp, reply_to, reply_after, playlist, infohash):
            assert isinstance(text, unicode)
            assert len(text) < 2^16
            assert isinstance(timestamp, (int, long)) 
            assert not reply_to or isinstance(reply_to, Packet)
            assert not reply_after or isinstance(reply_after, Packet)
            assert not playlist or isinstance(playlist, Packet)
            assert not infohash or isinstance(infohash, str), 'infohash is a %s'%type(infohash)
            assert not infohash or len(infohash) == 20, 'infohash has length %d'%len(infohash)
            
            super(CommentPayload.Implementation, self).__init__(meta)
            self._text = text
            self._timestamp = timestamp
            self._reply_to = reply_to
            self._reply_after = reply_after
            self._playlist = playlist
            self._infohash = infohash

        @property
        def text(self):
            return self._text
        
        @property
        def timestamp(self):
            return self._timestamp

        @property
        def reply_to(self):
            return self._reply_to

        @property
        def reply_after(self):
            return self._reply_after
        
        @property
        def playlist(self):
            return self._playlist
        
        @property
        def infohash(self):
            return self._infohash
        

class ModificationPayload(Payload):
    class Implementation(Payload.Implementation):
        def __init__(self, meta, modification, modification_on, latest_modification):
            assert isinstance(modification, dict)
            assert isinstance(modification_on, Packet)
            assert not latest_modification or isinstance(latest_modification, Packet)
            super(ModificationPayload.Implementation, self).__init__(meta)
            self._modification = modification
            self._modification_on = modification_on
            self._latest_modification = latest_modification

        @property
        def modification(self):
            return self._modification

        @property
        def modification_on(self):
            return self._modification_on
        
        @property
        def latest_modification(self):
            return self._latest_modification

class PlaylistTorrentPayload(Payload):
    class Implementation(Payload.Implementation):
        def __init__(self, meta, infohash, playlist):
            assert isinstance(infohash, str), 'infohash is a %s'%type(infohash)
            assert len(infohash) == 20, 'infohash has length %d'%len(infohash)
            assert isinstance(playlist, Packet)
            super(PlaylistTorrentPayload.Implementation, self).__init__(meta)
            self._infohash = infohash
            self._playlist = playlist

        @property
        def infohash(self):
            return self._infohash

        @property
        def playlist(self):
            return self._playlist

class MissingChannelPayload(Payload):
    pass