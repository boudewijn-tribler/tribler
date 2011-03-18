from hashlib import sha1

from conversion import AllChannelConversion
from preview import PreviewChannelCommunity
from payload import ChannelCastPayload, ChannelSearchRequestPayload, ChannelSearchResponsePayload

# from Tribler.Core.CacheDB.SqliteCacheDBHandler import TorrentDBHandler
# from Tribler.Core.SocialNetwork.RemoteTorrentHandler import RemoteTorrentHandler

from Tribler.Core.dispersy.bloomfilter import BloomFilter
from Tribler.Core.dispersy.dispersydatabase import DispersyDatabase
from Tribler.Core.dispersy.community import Community
from Tribler.Core.dispersy.conversion import DefaultConversion
from Tribler.Core.dispersy.message import Message, DropMessage
from Tribler.Core.dispersy.authentication import NoAuthentication
from Tribler.Core.dispersy.resolution import PublicResolution
from Tribler.Core.dispersy.distribution import DirectDistribution
from Tribler.Core.dispersy.destination import AddressDestination, CommunityDestination
from Tribler.Core.CacheDB.SqliteCacheDBHandler import ChannelCastDBHandler
from distutils.util import execute

if __debug__:
    from Tribler.Core.dispersy.dprint import dprint


CHANNELCAST_FIRST_MESSAGE = 30
CHANNELCAST_INTERVAL = 150

class AllChannelCommunity(Community):
    """
    A single community that all Tribler members join and use to disseminate .torrent files.

    The dissemination of .torrent files, using 'community-propagate' messages, is NOT done using a
    dispersy sync mechanism.  We prefer more specific dissemination mechanism than dispersy
    provides.  Dissemination occurs by periodically sending:

     - N most recently received .torrent files
     - M random .torrent files
     - O most recent .torrent files, created by ourselves
     - P randomly choosen .torrent files, created by ourselves
    """
    @classmethod
    def load_communities(cls, my_member, *args, **kargs):
        """
        Returns a list with all AllChannelCommunity instances that we are part off.

        Since there is one global AllChannelCommunity, we will return one using a static public
        master member key.
        """
        communities = super(AllChannelCommunity, cls).load_communities(*args, **kargs)

        if not communities:
            master_key = "3081a7301006072a8648ce3d020106052b81040027038192000403b2c94642d3a2228c2f274dcac5ddebc1b36da58282931b960ac19b0c1238bc8d5a17dfeee037ef3c320785fea6531f9bd498000643a7740bc182fae15e0461b158dcb9b19bcd6903f4acc09dc99392ed3077eca599d014118336abb372a9e6de24f83501797edc25e8f4cce8072780b56db6637844b394c90fc866090e28bdc0060831f26b32d946a25699d1e8a89b".decode("HEX")
            cid = sha1(master_key).digest()

            dispersy_database = DispersyDatabase.get_instance()
            dispersy_database.execute(u"INSERT OR IGNORE INTO community (user, classification, cid, public_key) VALUES (?, ?, ?, ?)",
                                      (my_member.database_id, cls.get_classification(), buffer(cid), buffer(master_key)))

            # new community instance
            community = cls(cid, master_key, *args, **kargs)

            # send out my initial dispersy-identity
            community.create_dispersy_identity()

            # add new community
            communities.append(community)

        return communities

    def __init__(self, cid, master_key):
        super(AllChannelCommunity, self).__init__(cid, master_key)
        
        # tribler channelcast database
        self._channelcast_db = ChannelCastDBHandler.getInstance()
        
        self._rawserver = self.dispersy.rawserver.add_task
        self._rawserver(self.create_channelcast, CHANNELCAST_FIRST_MESSAGE)

    @property
    def dispersy_sync_interval(self):
        # because there is nothing to sync in this community, we will only 'sync' once per hour
        return 3600.0

    def initiate_meta_messages(self):
        # Message(self, u"torrent-request", NoAuthentication(), PublicResolution(), DirectDistribution(), AddressDestination(), TorrentRequestPayload()),
        # Message(self, u"torrent-response", NoAuthentication(), PublicResolution(), DirectDistribution(), AddressDestination(), TorrentResponsePayload()),
        return [Message(self, u"channelcast", NoAuthentication(), PublicResolution(), DirectDistribution(), CommunityDestination(node_count=10), ChannelCastPayload(), self.check_channelcast, self.on_channelcast),
                Message(self, u"channel-search-request", NoAuthentication(), PublicResolution(), DirectDistribution(), CommunityDestination(node_count=10), ChannelSearchRequestPayload(), self.check_channel_search_request, self.on_channel_search_request),
                Message(self, u"channel-search-response", NoAuthentication(), PublicResolution(), DirectDistribution(), AddressDestination(), ChannelSearchResponsePayload(), self.check_channel_search_response, self.on_channel_search_response),
                ]

    def initiate_conversions(self):
        return [DefaultConversion(self), AllChannelConversion(self)]

    def create_channelcast(self, forward=True):
        sync_ids = self._channelcast_db.getRecentAndRandomTorrents()

        # select channel messages (associated with the sync_ids)
        packets = [packet for packet, in self._dispersy.database.execute(u"""
        SELECT sync.packet
        FROM sync
        WHERE sync.id IN (?)
        """, (u", ".join(map(unicode, sync_ids)),))]

        meta = self.get_meta_message(u"channelcast")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(self._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(packets))
        self._dispersy.store_update_forward([message], False, False, forward)
        
        self._rawserver(self.create_channelcast, CHANNELCAST_INTERVAL)
        return message

    def check_channelcast(self, messages):
        # no timeline check because NoAuthentication policy is used
        return messages

    def on_channelcast(self, messages):
        incoming_packets = []

        for message in messages:
            incoming_packets.extend((message.address, packet) for packet in message.payload.packets)

        for _, packet in incoming_packets:
            # ensure that all the PreviewChannelCommunity instances exist
            try:
                self._dispersy.get_community(packet[:20])
            except KeyError:
                if __debug__: dprint("join_community ", packet[:20].encode("HEX"))
                PreviewChannelCommunity.join_community(packet[:20], "", self._my_member)

        # handle all packets
        self._dispersy.on_incoming_packets(incoming_packets)

    # def _start_torrent_request_queue(self):
    #     # check that we are not working on a request already
    #     if not self._torrent_request_outstanding:
    #         while True:
    #             if not self._torrent_request_queue:
    #                 if __debug__: dprint("no more infohashes outstanding")
    #                 return

    #             address, infohash = self._torrent_request_queue.pop(0)
    #             if self._torrent_database._db.fetchone(u"SELECT 1 FROM Torrent WHERE infohash = ?", (infohash,)):
    #                 if __debug__: dprint("we already have this infohash")
    #                 continue

    #             # found an infohash to request
    #             break

    #         self.create_torrent_request(address, infohash, self._fulfill_torrent_request, (address,))
    #         self._torrent_request_outstanding = True

    # def _fulfill_torrent_request(self, address, message, req_address):
    #     if message:
    #         # todo: handle torrent insert
    #         pass

    #     else:
    #         # timeout on a request to req_address.  all requests to this address will likely
    #         # timeout, hence remove all these requests
    #         self._torrent_request_queue = [(address, infohash) for address, infohash in self._torrent_request_queue if not address == req_address]

    #     self._torrent_request_outstanding = False
    #     self._start_torrent_request_queue()

    # def create_torrent_request(self, address, infohash, response_func, response_args=(), timeout=10.0, store_and_forward=True):
    #     """
    #     Create a message to request a .torrent file.
    #     """
    #     assert isinstance(infohash, str)
    #     assert len(infohash) == 20
    #     assert hasattr(response_func, "__call__")
    #     assert isinstance(response_args, tuple)
    #     assert isinstance(timeout, float)
    #     assert timeout > 0.0
    #     assert isinstance(store_and_forward, bool)

    #     meta = self.get_meta_message(u"torrent-request")
    #     request = meta.implement(meta.authentication.implement(),
    #                              meta.distribution.implement(self._timeline.global_time),
    #                              meta.destination.implement(address),
    #                              meta.payload.implement(infohash))

    #     if store_and_forward:
    #         self._dispersy.store_and_forward([request])

    #     if response_func:
    #         meta = self.get_meta_message(u"torrent-response")
    #         footprint = meta.generate_footprint(payload=(infohash,))
    #         self._dispersy.await_message(footprint, response_func, response_args, timeout)

    #     return request

    # def on_torrent_request(self, address, message):
    #     """
    #     Received a 'torrent-request' message.
    #     """
    #     # we need to find the .torrent file and read the binary data
    #     torrent = self._torrent_database.getTorrent(message.payload.infohash)
    #     dprint(torrent, lines=1)
    #     if not (torrent and torrent["destination_path"] and os.path.isfile(torrent["destination_path"])):
    #         raise DropMessage("We do not have the requested infohash")
    #         return
    #     torrent_data = open(torrent["destination_path"], "r").read()

    #     # we need to find, optionally, some meta data such as associated 'channel', 'torrent', and
    #     # 'modify' messages.

    #     # todo: niels?
    #     # messages = [Message]

    #     meta = self.get_meta_message(u"torrent-response")
    #     response = meta.implement(meta.authentication.implement(),
    #                               meta.distribution.implement(self._timeline.global_time),
    #                               meta.destination.implement(address),
    #                               meta.payload.implement(message.payload.infohash, torrent_data, messages))

    #     self._dispersy.store_and_forward([message])

    # def on_torrent_response(self, address, message):
    #     """
    #     Received a 'torrent-response' message.
    #     """
    #     # we ignore this message because we get a different callback to match it to the request
    #     pass

    def create_channel_search_request(self, skip, search, response_func, response_args=(), timeout=10.0, method=u"simple-any-keyword", store=True, forward=True):
        """
        Create a message to request a remote channel search.
        """
        assert isinstance(skip, (tuple, list))
        assert not filter(lambda x: not isinstance(x, Message), skip)
        assert isinstance(search, (tuple, list))
        assert not filter(lambda x: not isinstance(x, unicode), search)
        assert isinstance(method, unicode)
        assert method in (u"simple-any-keyword", u"simple-all-keywords")
        assert hasattr(response_func, "__call__")
        assert isinstance(response_args, tuple)
        assert isinstance(timeout, float)
        assert timeout > 0.0

        # todo: we need to set a max items in the bloom filter to limit the size.  the bloom filter
        # be no more than +/- 1000 bytes large.
        skip_bloomfilter = BloomFilter(max(1, len(skip)), 0.1)
        map(skip_bloomfilter.add, (message.packet for message in skip))

        meta = self.get_meta_message(u"channel-search-request")
        request = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(self._timeline.global_time),
                                 meta.destination.implement(),
                                 meta.payload.implement(skip_bloomfilter, search, method))

        if response_func:
            meta = self.get_meta_message(u"channel-search-response")
            footprint = meta.generate_footprint(payload=(sha1(request.packet).digest(),))
            self._dispersy.await_message(footprint, response_func, response_args, timeout)

        self._dispersy.store_update_forward([request], store, False, forward)
        return request

    def check_channel_search_request(self, messages):
        for message in messages:
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message

    def on_channel_search_request(self, messages):
        """
        Received a 'channel-search-request' message.
        """
        responses = []
        for request in messages:
            # we need to find channels matching the search criteria

            packets = []

            # todo: niels?
            # packets = [packets]

            # we need to find, optionally, some meta data such as associated 'torrent', and 'modify'
            # messages.

            # todo: niels?
            # packets = [packets]

            meta = self.get_meta_message(u"channel-search-response")
            responses.append(meta.implement(meta.authentication.implement(),
                                            meta.distribution.implement(self._timeline.global_time),
                                            meta.destination.implement(address),
                                            meta.payload.implement(sha1(request.packet).digest(), packets)))
        self._dispersy.store_update_forward(responses, False, False, True)

    def check_channel_search_response(self, messages):
        for message in messages:
            if not self._timeline.check(message):
                yield DropMessage("TODO: implement delay by proof")
                continue
            yield message

    def on_channel_search_response(self, messages):
        """
        Received a 'channel-search-response' message.
        """
        # we ignore this message because we get a different callback to match it to the request
        pass