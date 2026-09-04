class NntpError(RuntimeError):
    pass


class NntpAuthenticationError(NntpError):
    pass


class NntpTemporaryError(NntpError):
    pass


class NntpArticleMissing(NntpError):
    pass


class NntpProtocolError(NntpError):
    pass


class NntpConfigurationError(NntpError):
    pass
