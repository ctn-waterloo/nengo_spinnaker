import pytest

from nengo_spinnaker.utils import collections as nscollections


def test_noneignoringlist():
    """Test a list which will not append None."""
    nil = nscollections.noneignoringlist()

    # We can append items normally
    nil.append(123)
    assert nil == [123]

    # Unless they're None
    nil.append(None)
    assert nil == [123]


def test_flatinsertionlist():
    """Test a list which will always flatten the items it inserts."""
    fil = nscollections.flatinsertionlist()

    # We can append items normally
    fil.append(123)
    assert fil == [123]

    # Unless they're lists
    fil.append([1, 2, 3])
    assert fil == [123, 1, 2, 3]


def test_registerabledict():
    """Test a dictionary that allows functions to be registered against it."""
    rd = nscollections.registerabledict()

    @rd.register("ABCD")
    def test_a():
        pass  # pragma : no cover

    assert rd["ABCD"] is test_a

    # Registering twice raises an error
    with pytest.raises(Exception) as excinfo:
        @rd.register("ABCD")
        def test_b():
            pass  # pragma : no cover
    assert "ABCD" in str(excinfo.value)

    # But this can be overridden
    @rd.register("ABCD", allow_overrides=True)
    def test_c():
        pass  # pragma : no cover


def test_mrolookupdict():
    """Test a dictionary which will look up items by going through their
    MROs.
    """
    class ParentA(object):
        pass

    class ChildA(ParentA):
        pass

    mdict = nscollections.mrolookupdict()
    mdict[ParentA] = 5

    assert mdict[ChildA] == 5

    mdict[ChildA] = 10
    assert mdict[ChildA] == 10

    # Objects not in the dictionary raise KeyErrors
    with pytest.raises(KeyError):
        mdict[object]


def test_counter():
    """Test an object which increments every time it is called."""
    counter = nscollections.counter()

    for i in range(10):
        assert counter() == i


def test_member_set():
    # Create two sets with different domains
    d1 = (1, 2, 3, 4)
    d2 = (5, 6, 7)

    set1 = nscollections.MemberSet(d1)
    set2 = nscollections.MemberSet(d2)

    # The sets are currently empty, ensure that this is the case.
    assert len(set1) == 0
    assert list(set1) == list()
    assert not any(d in set1 for d in d1)

    assert len(set2) == 0
    assert list(set2) == list()
    assert not any(d in set2 for d in d2)

    # Add an element to the set and ensure that it can be read out.
    set1.add(2)
    assert 2 in set1
    assert list(set1) == [2]
    assert len(set1) == 1

    # Adding an element that wasn't in the original domain should raise a
    # KeyError.
    with pytest.raises(KeyError):
        set1.add(7)

    # Testing for an element that wasn't in the original domain should raise a
    # KeyError.
    with pytest.raises(KeyError):
        7 in set1

    # The same for the 2nd set, has a different domain
    set2.add(5)
    set2.add(7)
    assert 5 in set2
    assert 7 in set2
    assert list(set2) == [5, 7]
    assert len(set2) == 2

    with pytest.raises(KeyError):
        set2.add(1)

    with pytest.raises(KeyError):
        1 in set2

    # Since the domains are different various pair-wise operations should fail.
    with pytest.raises(ValueError):
        set1.isdisjoint(set2)


def test_member_set_disjoint():
    # Create two sets with the same domains
    domain = (1, 2, 3, 4)
    a = nscollections.MemberSet(domain)
    b = nscollections.MemberSet(domain)

    # Add different elements to each set then test various pairwise operations.
    a.add(1)
    b.add(2)

    assert a.isdisjoint(b)
    assert b.isdisjoint(a)

    a.add(2)
    assert not a.isdisjoint(b)
    assert not b.isdisjoint(a)
