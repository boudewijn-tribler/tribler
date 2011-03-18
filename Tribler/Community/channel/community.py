from conversion import ChannelConversion
from payload import ChannelPayload, TorrentPayload, PlaylistPayload, CommentPayload, ModificationPayload, PlaylistTorrentPayload, MissingChannelPayload

from Tribler.Core.CacheDB.SqliteCacheDBHandler import ChannelCastDBHandler
from Tribler.Core.CacheDB.sqlitecachedb import bin2str

from Tribler.Core.SocialNetwork.RemoteTorrentHandler import RemoteTorrentHandler

from Tribler.Core.dispersy.bloomfilter import BloomFilter
from Tribler.Core.dispersy.dispersydatabase import DispersyDatabase
from Tribler.Core.dispersy.community import Community
from Tribler.Core.dispersy.conversion import DefaultConversion
from Tribler.Core.dispersy.message import Message, DropMessage
from message import DelayMessageReqChannelMessage
from Tribler.Core.dispersy.authentication import MemberAuthentication, NoAuthentication
from Tribler.Core.dispersy.resolution import LinearResolution, PublicResolution
from Tribler.Core.dispersy.distribution import FullSyncDistribution, DirectDistribution
from Tribler.Core.dispersy.destination import CommunityDestination, AddressDestination
from Tribler.Core.dispersy.member import MyMember

if __debug__:
    from Tribler.Core.dispersy.dprint import dprint

class ChannelCommunity(Community):
    """
    Each user owns zero or more ChannelCommunities that other can join and use to discuss.
    """
    def __init__(self, cid, master_key):
        super(ChannelCommunity, self).__init__(cid, master_key)

        # tribler channelcast database
        self._channelcast_db = ChannelCastDBHandler.getInstance()

        # tribler channel_id
        self.channel_id = self._channelcast_db._db.fetchone(u"SELECT id FROM Channels WHERE dispersy_cid = ?", (buffer(self._cid),))
        self._rawserver = self._dispersy.rawserver.add_task

    def initiate_meta_messages(self):
        return [Message(self, u"channel", MemberAuthentication(encoding="sha1"), LinearResolution(), FullSyncDistribution(enable_sequence_number=False, synchronization_direction=u"out-order"), CommunityDestination(node_count=10), ChannelPayload(), self._disp_check_channel, self._disp_on_channel),
                Message(self, u"torrent", MemberAuthentication(encoding="sha1"), LinearResolution(), FullSyncDistribution(enable_sequence_number=False, synchronization_direction=u"random-order"), CommunityDestination(node_count=10), TorrentPayload(), self._disp_check_torrent, self._disp_on_torrent),
                Message(self, u"playlist", MemberAuthentication(encoding="sha1"), LinearResolution(), FullSyncDistribution(enable_sequence_number=False, synchronization_direction=u"out-order"), CommunityDestination(node_count=10), PlaylistPayload(), self._disp_check_playlist, self._disp_on_playlist),
                Message(self, u"comment", MemberAuthentication(encoding="sha1"), LinearResolution(), FullSyncDistribution(enable_sequence_number=False, synchronization_direction=u"out-order"), CommunityDestination(node_count=10), CommentPayload(), self._disp_check_comment, self._disp_on_comment),
                Message(self, u"modification", MemberAuthentication(encoding="sha1"), LinearResolution(), FullSyncDistribution(enable_sequence_number=False, synchronization_direction=u"out-order"), CommunityDestination(node_count=10), ModificationPayload(), self._disp_check_modification, self._disp_on_modification),
                Message(self, u"playlist_torrent", MemberAuthentication(encoding="sha1"), LinearResolution(), FullSyncDistribution(enable_sequence_number=False, synchronization_direction=u"out-order"), CommunityDestination(node_count=10), PlaylistTorrentPayload(), self._disp_check_playlist_torrent, self._disp_on_playlist_torrent),
                Message(self, u"missing-channel", NoAuthentication(), PublicResolution(), DirectDistribution(), AddressDestination(), MissingChannelPayload(), self._disp_check_missing_channel, self._disp_on_missing_channel),
                ]

    def initiate_conversions(self):
        return [DefaultConversion(self), ChannelConversion(self)]

    def create_channel(self, name, description, store=True, update=True, forward=True):
        def dispersy_thread():
            self._disp_create_channel(name, description, store, update, forward)
        self._rawserver(dispersy_thread)
    
    def _disp_create_channel(self, name, description, store=True, update=True, forward=True):
        meta = self.get_meta_message(u"channel")
        message = meta.implement(meta.authentication.implement(self._my_member),
                                 meta.distribution.implement(self._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(name, description))
        self._dispersy.store_update_forward([message], store, update, forward)
        return message

    def _disp_check_channel(self, messages):
        for message in messages:
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message

    def _disp_on_channel(self, messages):
        for message in messages:
            if __debug__: dprint(message)

            authentication_member = message.authentication.member
            if isinstance(authentication_member, MyMember):
                peer_id = None
            else:
                peer_id = self._channelcast_db._db.getPeerID(authentication_member.public_key)

            self.channel_id = self._channelcast_db.on_channel_from_dispersy(self._cid, peer_id, message.payload.name, message.payload.description)

    def _disp_create_torrent(self, infohash, timestamp, store=True, update=True, forward=True):
        meta = self.get_meta_message(u"torrent")
        message = meta.implement(meta.authentication.implement(self._my_member),
                                 meta.distribution.implement(self._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(infohash, timestamp))
        self._dispersy.store_update_forward([message], store, update, forward)
        return message
    
    def _disp_create_torrents(self, torrentlist, store=True, update=True, forward=True):
        messages = []
        
        meta = self.get_meta_message(u"torrent")
        for infohash, timestamp in torrentlist:
            message = meta.implement(meta.authentication.implement(self._my_member),
                                     meta.distribution.implement(self._timeline.claim_global_time()),
                                     meta.destination.implement(),
                                     meta.payload.implement(infohash, timestamp))
            messages.append(message)
        self._dispersy.store_update_forward(messages, store, update, forward)
        return messages

    def _disp_check_torrent(self, messages):
        for message in messages:
            if not self.channel_id:
                yield DelayMessageReqChannelMessage(message)
                continue
                
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message

    def _disp_on_torrent(self, messages):
        torrentlist = []
        for message in messages:
            if __debug__: dprint(message)
            dispersy_id = message.packet_id
            torrentlist.append((self.channel_id, dispersy_id, message.payload.infohash, message.payload.timestamp))
        self._channelcast_db.on_torrents_from_dispersy(torrentlist)

    #create, check or receive playlist
    def create_playlist(self, name, description, infohashes = [], store=True, update=True, forward=True):
        def dispersy_thread():
            message = self._disp_create_playlist.create_playlist(name, description)
            self._disp_create_playlist_torrents(infohashes, message, store, update, forward)
    
        self._rawserver(dispersy_thread)

    def _disp_create_playlist(self, name, description, store=True, update=True, forward=True):
        meta = self.get_meta_message(u"playlist")
        message = meta.implement(meta.authentication.implement(self._my_member),
                                 meta.distribution.implement(self._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(name, description))
        self._dispersy.store_update_forward([message], store, update, forward)
        return message

    def _disp_check_playlist(self, messages):
        for message in messages:
            if not self.channel_id:
                yield DelayMessageReqChannelMessage(message)
                continue
            
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message

    def _disp_on_playlist(self, messages):
        for message in messages:
            if __debug__: dprint(message)
            dispersy_id = message.packet_id
            self._channelcast_db.on_playlist_from_dispersy(self.channel_id, dispersy_id, message.payload.name, message.payload.description)

    #create, check or receive comments
    def create_comment(self, text, timestamp, reply_to, reply_after, playlist_id, infohash, store=True, update=True, forward=True):
        def dispersy_thread():
            reply_to_message = reply_to
            reply_after_message = reply_after
            playlist_message = playlist_id
            
            if reply_to:
                reply_to_message = self._get_message_from_dispersy_id(reply_to, 'comment')
            if reply_after:
                reply_after_message = self._get_message_from_dispersy_id(reply_after, 'comment')
            if playlist_id:
                playlist_message = self._get_message_from_playlist_id(playlist_id)
            self._disp_create_comment(text, timestamp, reply_to_message, reply_after_message, playlist_message, infohash, store, update, forward)
    
        self._rawserver(dispersy_thread)

    def _disp_create_comment(self, text, timestamp, reply_to_message, reply_after_message, playlist_message, infohash, store=True, update=True, forward=True):
        meta = self.get_meta_message(u"comment")
        message = meta.implement(meta.authentication.implement(self._my_member),
                                 meta.distribution.implement(self._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(text, timestamp, reply_to_message, reply_after_message, playlist_message, infohash))
        self._dispersy.store_update_forward([message], store, update, forward)
        return message

    def _disp_check_comment(self, messages):
        for message in messages:
            if not self.channel_id:
                yield DelayMessageReqChannelMessage(message)
                continue
            
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message
    
    def _disp_on_comment(self, messages):
        for message in messages:
            if __debug__: dprint(message)

            dispersy_id = message.packet_id
            
            authentication_member = message.authentication.member
            if isinstance(authentication_member, MyMember):
                peer_id = None
            else:
                peer_id = self._channelcast_db._db.getPeerID(authentication_member.public_key)
            
            reply_to_id = None
            if message.payload.reply_to:
                reply_to_id = message.payload.reply_to.packet_id
            
            reply_after_id = None
            if message.payload.reply_after:
                reply_after_id = message.payload.reply_after.packet_id
            
            playlist_dispersy_id = None
            if message.payload.playlist:
                playlist_dispersy_id = message.payload.playlist.packet_id
            self._channelcast_db.on_comment_from_dispersy(self.channel_id, dispersy_id, peer_id, message.payload.text, message.payload.timestamp, reply_to_id , reply_after_id, playlist_dispersy_id, message.payload.infohash)
        
    #modify channel, playlist or torrent
    def modifyChannel(self, channel_id, modifications, store=True, update=True, forward=True):
        def dispersy_thread():
            modification_on_message = self._get_message_from_channel_id(channel_id)
            latest_modification = self._get_latest_modification_from_channel_id(channel_id)
            self._disp_create_modification(modifications, modification_on_message, latest_modification, store, update, forward)
        
        self._rawserver(dispersy_thread)
        
    def modifyPlaylist(self, playlist_id, modifications, store=True, update=True, forward=True):
        def dispersy_thread():
            modification_on_message = self._get_message_from_playlist_id(playlist_id)
            latest_modification = self._get_latest_modification_from_playlist_id(playlist_id)
            self._disp_create_modification(modifications, modification_on_message, latest_modification, store, update, forward)
        
        self._rawserver(dispersy_thread)
    
    def modifyTorrent(self, channeltorrent_id, modifications, store=True, update=True, forward=True):
        def dispersy_thread():
            modification_on_message = self._get_message_from_torrent_id(channeltorrent_id)
            latest_modification = self._get_latest_modification_from_torrent_id(channeltorrent_id)
            
            self._disp_create_modification(modifications, modification_on_message, latest_modification, store, update, forward)
        self._rawserver(dispersy_thread)
        
    def _disp_create_modification(self, modification, modification_on, latest_modification, store=True, update=True, forward=True):
        meta = self.get_meta_message(u"modification")
        message = meta.implement(meta.authentication.implement(self._my_member),
                                 meta.distribution.implement(self._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(modification, modification_on, latest_modification))
        self._dispersy.store_update_forward([message], store, update, forward)
        return message

    def _disp_check_modification(self, messages):
        for message in messages:
            if not self.channel_id:
                yield DelayMessageReqChannelMessage(message)
                continue
            
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message

    def _disp_on_modification(self, messages):
        for message in messages:
            if __debug__: dprint(message)
            message_name = message.payload.modification_on.name
        
            modification_dict = message.payload.modification
            modifying_dispersy_id = message.payload.modification_on.packet_id
            latest_dispersy_modifier = message.packet_id
        
            if message_name ==  u"torrent":
                self._channelcast_db.on_torrent_modification_from_dispersy(modifying_dispersy_id, modification_dict, latest_dispersy_modifier)
        
            elif message_name == u"playlist":
                self._channelcast_db.on_playlist_modification_from_dispersy(modifying_dispersy_id, modification_dict, latest_dispersy_modifier)
        
            elif message_name == u"channel":
                self._channelcast_db.on_channel_modification_from_dispersy(self._cid, modification_dict, latest_dispersy_modifier)
            
    #create, check or receive playlist_torrent message
    def create_playlist_torrents(self, infohashes, playlist_id, store=True, update=True, forward=True):
        def dispersy_thread():
            message = self._get_message_from_playlist_id(playlist_id)
            self._disp_create_playlist_torrents(infohashes, message, store, update, forward)
            
        self._rawserver(dispersy_thread)
        
    def _disp_create_playlist_torrents(self, infohashes, playlist_message, store=True, update=True, forward=True):
        meta = self.get_meta_message(u"playlist_torrent")
        messages = []
        for infohash in infohashes:
            message = meta.implement(meta.authentication.implement(self._my_member),
                                     meta.distribution.implement(self._timeline.claim_global_time()),
                                     meta.destination.implement(),
                                     meta.payload.implement(infohash, playlist_message))
            messages.append(message)

        self._dispersy.store_update_forward(messages, store, update, forward)
        return message
    
    def _disp_check_playlist_torrent(self, address, messages):
        for message in messages:
            if not self.channel_id:
                yield DelayMessageReqChannelMessage(message)
                continue
            
            if not self._timeline.check(message):
                raise DropMessage("TODO: implement delay by proof")
            yield message
    
    def _disp_on_playlist_torrent(self, address, messages):
        for message in messages:
            
            playlist_dispersy_id = message.payload.playlist.packet_id
            self._channelcast_db.on_playlist_torrent(playlist_dispersy_id, message.payload.infohash)
            
    #check or receive missing channel message
    def _disp_check_missing_channel(self, address, messages):
        for message in messages:
            yield message

    def _disp_on_missing_channel(self, address, messages):
        # 1. get the packet
        try:
            packet, packet_id = self._dispersy.database.execute(u"SELECT sync.packet, sync.id FROM sync JOIN name ON sync.name = name.id WHERE name.value = ? ORDER BY global_time DESC", ('channel',)).next()
        except StopIteration:
            raise RuntimeError("Could not find requested packet")
        
        # 2. convert packet into a Message instance
        try:
            message = self.get_conversion(packet[:22]).decode_message(("", -1), packet)
        except ValueError:
            raise RuntimeError("Unable to decode packet")
        message.packet_id = packet_id
        
        # 3. send back to peer
        self._dispersy._send([address], [message])
        
    #helper functions
    def _get_message_from_channel_id(self, channel_id):
        assert isinstance(channel_id, (int, long))
        # 1. get the dispersy identifier from the channel_id
        dispersy_id = self._channelcast_db._db.fetchone(u"SELECT dispersy_id FROM Channels WHERE id = ?", (channel_id,))

        # 2. get the message
        message = self._get_message_from_dispersy_id(dispersy_id, 'channel')
        return message
    
    def _get_latest_modification_from_channel_id(self, channel_id):
        assert isinstance(channel_id, (int, long))
        # 1. get the dispersy identifier from the channel_id
        dispersy_id = self._channelcast_db._db.fetchone(u"SELECT latest_dispersy_modifier FROM Channels WHERE id = ?", (channel_id,))
        
        if dispersy_id:
            # 2. get the message
            message = self._get_message_from_dispersy_id(dispersy_id, 'modification')
            return message
        
    def _get_message_from_playlist_id(self, playlist_id):
        assert isinstance(playlist_id, (int, long))
        # 1. get the dispersy identifier from the channel_id
        dispersy_id = self._channelcast_db._db.fetchone(u"SELECT dispersy_id FROM Playlists WHERE id = ?", (playlist_id,))

        # 2. get the message
        message = self._get_message_from_dispersy_id(dispersy_id, 'playlist')
        return message
    
    def _get_latest_modification_from_playlist_id(self, playlist_id):
        assert isinstance(playlist_id, (int, long))
        # 1. get the dispersy identifier from the channel_id
        dispersy_id = self._channelcast_db._db.fetchone(u"SELECT latest_dispersy_modifier FROM Playlists WHERE id = ?", (playlist_id,))

        if dispersy_id:
            # 2. get the message
            message = self._get_message_from_dispersy_id(dispersy_id, 'playlist')
            return message
        
    def _get_message_from_torrent_id(self, torrent_id):
        assert isinstance(torrent_id, (int, long))

        # 1. get the dispersy identifier from the channel_id
        dispersy_id = self._channelcast_db._db.fetchone(u"SELECT dispersy_id FROM ChannelTorrents WHERE id = ?", (torrent_id,))
        
        # 2. get the message
        message = self._get_message_from_dispersy_id(dispersy_id, "torrent")
        return message
    
    def _get_latest_modification_from_torrent_id(self, torrent_id):
        assert isinstance(torrent_id, (int, long))

        # 1. get the dispersy identifier from the channel_id
        dispersy_id = self._channelcast_db._db.fetchone(u"SELECT latest_dispersy_modifier FROM ChannelTorrents WHERE id = ?", (torrent_id,))
        if dispersy_id:
        
            # 2. get the message
            message = self._get_message_from_dispersy_id(dispersy_id, "modification")
            return message
        
    def _get_message_from_dispersy_id(self, dispersy_id, messagename):
        # 1. get the packet
        try:
            cid, packet, packet_id = self._dispersy.database.execute(u"SELECT community.cid, sync.packet, sync.id FROM community JOIN sync ON sync.community = community.id WHERE sync.id = ?", (dispersy_id,)).next()
        except StopIteration:
            raise RuntimeError("Unknown dispersy_id")
        
        cid = str(cid)
        packet = str(packet)
        # 2. get the community instance from the 20 byte identifier
        try:
            community = self._dispersy.get_community(cid)
        except KeyError:
            raise RuntimeError("Unknown community identifier")

        # 3. convert packet into a Message instance
        try:
            message = community.get_conversion(packet[:22]).decode_message(("", -1), packet)
        except ValueError, v:
            #raise RuntimeError("Unable to decode packet")
            raise
        message.packet_id = packet_id
        
        # 4. check
        assert message.name == messagename, "Expecting a '%s' message"%messagename
       
        return message