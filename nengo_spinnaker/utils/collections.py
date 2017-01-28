from __future__ import absolute_import
from bitarray import bitarray
import collections


class noneignoringlist(list):
    """List which will not append None.

    For example::

        >>> nil = noneignoringlist()
        >>> nil.append(234)
        >>> nil
        [234]
        >>> nil.append(None)
        >>> nil
        [234]

    However, if you manually assign an element to `None` then it will be
    assigned as usual.::

        >>> nil[0] = None
        >>> nil
        [None]
    """

    def append(self, x):
        """Appends `x` to the end of the list unless it is `None`."""
        if x is not None:
            super(noneignoringlist, self).append(x)


class flatinsertionlist(list):
    """List which will extend rather than append when appending lists,
    resulting in a list which is flattened on insertion.

    For example::

        >>> fil = flatinsertionlist()
        >>> fil.append(5)
        >>> fil
        [5]
        >>> fil.append([1, 2, 3])
        >>> fil
        [5, 1, 2, 3]

    However, if you manually assign a list to an item then it will be assigned
    as usual.::

        >>> fil[0] = [5, 4]
        >>> fil
        [[5, 4], 1, 2, 3]
    """

    def append(self, x):
        """Appends `x` to the list, unless it is an iterable, in which case the
        list will be extended.
        """
        if isinstance(x, collections.Iterable):
            self.extend(x)
        else:
            super(flatinsertionlist, self).append(x)


class registerabledict(dict):
    """A dictionary with a decorator that allows easy entry of functions into
    the dict.

    For example::

        >>> fns = registerabledict()
        >>>
        >>> @fns.register("ABCD")
        ... def say_hello():
        ...     print("Moni, muli bwanji?")
        >>>
        >>> fns["ABCD"]()
        Moni, muli bwanji?

    Registering against the same key twice will result in an error:

        >>> @fns.register("ABCD")
        ... def say_hello_2():
        ...     print("Bonjour")
        Traceback (most recent call last):
        Exception: ABCD: key already in dictionary

    Although this may be overridden:

        >>> @fns.register("ABCD", allow_overrides=True)
        ... def say_hello_3():
        ...     print("Guten tag")
        >>>
        >>> fns["ABCD"]()
        Guten tag
    """

    def register(self, key, allow_overrides=False):
        """Decorator which allows registering of functions as entries in the
        dictionary.
        """
        if key in self and not allow_overrides:
            raise Exception("{}: key already in dictionary".format(key))

        def decorator(f):
            self[key] = f
            return f

        return decorator


class mrolookupdict(dict):
    """A dictionary with classes as keys and MRO-searching look-up behaviour.

    Each entry in the dictionary has a class as its key.  When a look-up is
    performed the MRO of the class being looked up is used to determine which
    entries are relevant and the first matching entry is returned.

    For example::

        >>> class SimpleObject(object):
        ...     pass
        >>>
        >>> class DerivedObject(SimpleObject):
        ...     pass
        >>>
        >>>
        >>> mrodict = mrolookupdict()
        >>> mrodict[SimpleObject] = 5
        >>>
        >>> mrodict[SimpleObject]
        5
        >>> mrodict[DerivedObject]  # Uses the MRO to find a value
        5

    `KeyError`s are raised if a suitable class can't be found in the
    dictionary::

        >>> class NotDerivedObject(object):
        ...     pass
        >>>
        >>> mrodict[NotDerivedObject]
        Traceback (most recent call last):
        KeyError: <class 'nengo_spinnaker.utils.collections.NotDerivedObject'>
    """
    def __getitem__(self, cls):
        """Get the first matching entry from the class MRO."""
        for t in cls.__mro__:
            if t in self:
                return super(mrolookupdict, self).__getitem__(t)
        else:
            raise KeyError(cls)


class counter(object):
    """A counter which can be used with `defaultdict` to assign unique integers
    to objects.
    """
    def __init__(self):
        self._count = -1

    def __call__(self):
        self._count += 1
        return self._count


class MemberSet(object):
    """A set-like type which can store members of a given set of elements.
    """
    # A class-wide mapping from domains to an ordering of the elements of the
    # domain.
    domains = dict()

    def __init__(self, domain):
        # Store a reference to the domain and the ordering, creating a new
        # ordering if it hasn't previously been observed.
        self._domain = domain

        if domain not in MemberSet.domains:
            MemberSet.domains[domain] = {e: i for i, e in enumerate(domain)}
        self._domain_ordering = MemberSet.domains[domain]

        # Create a bitstring containing sufficient room to represent which
        # elements of the domain are present in the set.
        self._elements = bitarray(len(self._domain))
        self._elements.setall(False)

    def __iter__(self):
        for bit, elem in zip(self._elements, self._domain):
            if bit:
                yield elem

    def _get_index(self, elem):
        return self._domain_ordering[elem]

    def __len__(self):
        return self._elements.count()

    def add(self, elem):
        # Get the bit position from the ordering and then add it
        self._elements[self._get_index(elem)] = True

    def __contains__(self, elem):
        # Get the bit position from the ordering and then test
        return self._elements[self._get_index(elem)]

    def isdisjoint(self, other):
        """Return True if the set has no elements in common with other.

        Sets are disjoint if and only if their intersection is the empty set.
        """
        # Check that the sets have equivalent domains
        if self._domain is not other._domain:
            raise ValueError("Cannot compare sets with different domains.")

        # The intersection of the sets should be empty
        intersection = self._elements & other._elements
        return not intersection.any()
