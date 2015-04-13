import collections

from rig.bitfield import BitField


class Keyspace(BitField):
    """Represent and derive keyspaces for use in multicast packets.

    Nengo/SpiNNaker enforces some additional rules about the structure of
    keyspaces.  It is often necessary to have a field in the key which
    indicates which component of a vector the multicast packet represents; the
    method `add_index_field` can be used to add an index field to a keyspace
    with a given namespace, and `get_with_index` will return a new keyspace
    with the field set.  For example::

        >>> ks = Keyspace()
        >>> ks.get_index()
        Traceback (most recent call last):
        ValueError: Keyspace does not have an index field
        >>> ks.add_index_field("nengo")
        >>> x = ks.get_with_index(15)
        >>> x.get_index()
        15

    Attempting to add an additional index field will fail.::

        >>> ks.add_index_field("oops")
        Traceback (most recent call last):
        ValueError: Keyspace already has an index field, "nengo_index"

    The method `get_index_mask` can be used to retrieve the mask from the
    keyspace.::

        >>> ks.assign_fields()
        >>> hex(ks.get_index_mask())
        '0xf'
    """
    def _get_index_identifier(self, raise_if_missing=True):
        """Return the identifier associated with the index field in this
        keyspace.
        """
        for identifier, _ in self._enabled_fields():
            if "index" == identifier[-5:]:
                return identifier
        else:
            if raise_if_missing:
                raise ValueError("Keyspace does not have an index field")

    def add_index_field(self, namespace):
        """Add a field which represents which component of a vector is being
        represented by the multicast packet.

        Parameters
        ----------
        namespace : string
            Namespace the index field should be added to.
        """
        # Check that we don't already have an index field
        identifier = self._get_index_identifier(raise_if_missing=False)
        if identifier is not None:
            raise ValueError(
                "Keyspace already has an index field, \"{}\"".format(
                    identifier)
            )

        # Add the index field
        self.add_field("{}_index".format(namespace), start_at=0)

    def get_index(self):
        """Return the value of the index field for this keyspace."""
        identifier = self._get_index_identifier()
        return getattr(self, identifier)

    def get_with_index(self, value):
        """Return a derived keyspace with the index field set."""
        identifier = self._get_index_identifier()
        return self(**{identifier: value})

    def get_with_indices(self, values, max_v=None):
        """Get a generator of keyspaces with the index field filled in with the
        given values.

        For example::

            >>> ks = Keyspace()
            >>> ks.add_index_field("nengo")
            >>> for x in ks.get_with_indices((slice(0, 5), 5, 6, 7,
            ...                               slice(8, 10))):
            ...     print(x)
            <32-bit BitField 'nengo_index':0>
            <32-bit BitField 'nengo_index':1>
            <32-bit BitField 'nengo_index':2>
            <32-bit BitField 'nengo_index':3>
            <32-bit BitField 'nengo_index':4>
            <32-bit BitField 'nengo_index':5>
            <32-bit BitField 'nengo_index':6>
            <32-bit BitField 'nengo_index':7>
            <32-bit BitField 'nengo_index':8>
            <32-bit BitField 'nengo_index':9>

        The minimum value for a slice is taken to be zero, but the max value
        can be specified:

            >>> for x in ks.get_with_indices(slice(None), max_v=3):
            ...     print(x)
            <32-bit BitField 'nengo_index':0>
            <32-bit BitField 'nengo_index':1>
            <32-bit BitField 'nengo_index':2>

        A `ValueError` is raised if these values are missing.

            >>> list(ks.get_with_indices(slice(None)))
            Traceback (most recent call last):
            ValueError: no stop value specified
        """
        def _get_with_indices(v):
            if isinstance(v, slice):
                if max_v is None and v.stop is None:
                    raise ValueError("no stop value specified")

                start = 0 if v.start is None else v.start
                stop = max_v if v.stop is None else v.stop
                step = 1 if v.step is None else v.step

                for i in range(start, stop, step):
                    yield self.get_with_index(i)
            else:
                yield self.get_with_index(v)

        if isinstance(values, collections.Iterable):
            for v in values:
                for x in _get_with_indices(v):
                    yield x
        else:
            for x in _get_with_indices(values):
                yield x

    def get_index_mask(self):
        """Return the mask required to extract the index field."""
        identifier = self._get_index_identifier()
        return self.get_mask(field=identifier)


class KeyspaceContainer(collections.defaultdict):
    """A container which can recall or allocate specific keyspaces to modules
    and users on request.

    A region of the keyspace ("user") is updated to indicate to which user the
    keyspace belongs.

    The default keyspace can be obtained by requesting the keyspace with the
    name "nengo".

        >>> ksc = KeyspaceContainer()
        >>> default_ks = ksc["nengo"]
        >>> isinstance(default_ks, Keyspace)
        True
        >>> default_ks.get_tags('nengo_object') == {ksc.routing_tag,
        ...                                         ksc.filter_routing_tag}
        True
        >>> default_ks.get_tags('nengo_connection') == {ksc.routing_tag,
        ...                                             ksc.filter_routing_tag}
        True
        >>> default_ks.get_tags('nengo_cluster') == {ksc.routing_tag}
        True
        >>> default_ks
        <32-bit BitField 'user':0, 'nengo_object':?, 'nengo_cluster':?, \
'nengo_connection':?, 'nengo_index':?>

    Additional keyspaces can be requested and are automagically created.

        >>> new_ks = ksc["new_user"]
        >>> new_ks
        <32-bit BitField 'user':1>

        >>> new_ks2 = ksc["new_user2"]
        >>> new_ks2
        <32-bit BitField 'user':2>

    ..warning::
        Namespacing should be used to avoid collisions between keyspaces.

    ..warning::
        The `user` field is reserved for this container.

    Re-requesting an existing keyspace simply returns the existing one.

        >>> ksc["new_user"]
        <32-bit BitField 'user':1>
        >>> ksc["new_user"] is new_ks
        True
        >>> ksc["new_user"] is not new_ks2
        True

    The routing and filter routing tags are also exposed through this interface
    as strings.

        >>> ksc.routing_tag
        'routing'
        >>> ksc.filter_routing_tag
        'filter_routing'

    Finally, field sizes may be fixed.

        >>> # Before fixing trying to get a mask fails
        >>> new_ks.get_mask(tag=ksc.routing_tag)
        Traceback (most recent call last):
        ValueError: Field 'user' does not have a fixed size/position.

        >>> # After fixing it works fine
        >>> ksc.assign_fields()
        >>> hex(new_ks.get_mask(tag=ksc.routing_tag))
        '0x30'

    The default fields and their tags:

    ==================   =======================
    Field                Tags
    ==================   =======================
    `nengo_object`       routing, filter routing
    `nengo_cluster`      routing
    `nengo_connection`   routing, filter routing
    `nengo_dimension`
    ==================   =======================

    `nengo_cluster` is only used for objects which are split across multiple
    chips to indicate which chip they are located on (all is needed is a simple
    count).
    """
    class _KeyspaceGetter(object):
        def __init__(self, ks):
            self._count = 0
            self._ks = ks

        def __call__(self):
            new_ks = self._ks(user=self._count)
            self._count += 1
            return new_ks

    def __init__(self, routing_tag="routing",
                 filter_routing_tag="filter_routing"):
        """Create a new keyspace container with the given tags for routing and
        filter routing.
        """
        # The tags
        self._routing_tag = routing_tag
        self._filter_routing_tag = filter_routing_tag

        # The keyspaces
        self._master_keyspace = _master_keyspace = Keyspace(length=32)
        _master_keyspace.add_field(
            "user", tags=[self.routing_tag, self.filter_routing_tag])

        # Initialise the defaultdict behaviour
        super(KeyspaceContainer, self).__init__(
            self._KeyspaceGetter(_master_keyspace))

        # Add the default keyspace
        nengo_ks = self["nengo"]
        nengo_ks.add_field("nengo_object", tags=[self.routing_tag,
                                                 self.filter_routing_tag])
        nengo_ks.add_field("nengo_cluster", tags=[self.routing_tag])
        nengo_ks.add_field("nengo_connection", tags=[self.routing_tag,
                                                     self.filter_routing_tag])
        nengo_ks.add_index_field("nengo")

    def assign_fields(self):
        """Call `assign_fields` on the master keyspace, forcing field
        assignation for all keyspaces.
        """
        self._master_keyspace.assign_fields()

    @property
    def routing_tag(self):
        """The tag used in creating routing table entries."""
        return self._routing_tag

    @property
    def filter_routing_tag(self):
        """The tag used in creating filter routing table entries."""
        return self._filter_routing_tag


keyspaces = KeyspaceContainer()
"""The global set of keyspaces."""


def is_nengo_keyspace(keyspace):
    """Return True if the keyspace is the default Nengo keyspace.

    Example::

        >>> ksc = KeyspaceContainer()
        >>> is_nengo_keyspace(ksc["nengo"])
        True

        >>> is_nengo_keyspace(ksc["not_nengo"])
        False

    Parameters
    ----------
    keyspace : :py:class:`rig.bitfield.BitField`
        Bitfield representation of keyspace.

    Returns
    -------
    bool
        True if the bitspace is a member of the class of Nengo keyspaces.
    """
    return keyspace.user == 0
