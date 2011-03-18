from Tribler.Core.dispersy.message import DelayMessage

class DelayMessageReqChannelMessage(DelayMessage):
    """
    Raised during ChannelCommunity.check_ if the channel message has not been received yet.
    """
    def __init__(self, delayed):
        if __debug__:
            from Tribler.Core.dispersy.message import Message
        assert isinstance(delayed, Message.Implementation)
        # the footprint that will trigger the delayed packet
        footprint = "".join(("channel",
                             " Community:", delayed.community.cid.encode("HEX")))

        # the request message that asks for the message that will
        # trigger the delayed packet
        meta = delayed.community.get_meta_message(u"missing-channel")
        message = meta.implement(meta.authentication.implement(),
                                 meta.distribution.implement(delayed.community._timeline.claim_global_time()),
                                 meta.destination.implement(),
                                 meta.payload.implement(delayed.authentication.member, delayed.meta))

        super(DelayMessageReqChannelMessage, self).__init__("Missing channel-message", footprint, message.packet)