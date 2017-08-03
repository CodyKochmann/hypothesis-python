# coding=utf-8
#
# This file is part of Hypothesis, which may be found at
# https://github.com/HypothesisWorks/hypothesis-python
#
# Most of this work is copyright (C) 2013-2017 David R. MacIver
# (david@drmaciver.com), but it contains contributions by others. See
# CONTRIBUTING.rst for a full list of people who may hold copyright, and
# consult the git log if you need to determine who owns an individual
# contribution.
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.
#
# END HEADER

from __future__ import division, print_function, absolute_import

import pytest

import hypothesis.strategies as st
from hypothesis import Verbosity, find, given, assume, settings
from hypothesis.errors import NoSuchExample, Unsatisfiable
from hypothesis.database import SQLiteExampleDatabase, \
    InMemoryExampleDatabase


def test_saves_incremental_steps_in_database():
    key = b"a database key"
    database = SQLiteExampleDatabase(':memory:')
    find(
        st.binary(min_size=10), lambda x: any(x),
        settings=settings(database=database), database_key=key
    )
    assert len(set(database.fetch(key))) > 1


def test_clears_out_database_as_things_get_boring():
    key = b"a database key"
    database = SQLiteExampleDatabase(':memory:')
    do_we_care = True

    def stuff():
        try:
            find(
                st.binary(min_size=50), lambda x: do_we_care and any(x),
                settings=settings(database=database, max_examples=10),
                database_key=key
            )
        except NoSuchExample:
            pass
    stuff()
    assert len(set(database.fetch(key))) > 1
    do_we_care = False
    stuff()
    initial = len(set(database.fetch(key)))
    assert initial > 0

    for _ in range(initial):
        stuff()
        keys = set(database.fetch(key))
        if not keys:
            break
    else:
        assert False


def test_trashes_all_invalid_examples():
    key = b"a database key"
    database = SQLiteExampleDatabase(':memory:')
    finicky = False

    def stuff():
        try:
            find(
                st.binary(min_size=100),
                lambda x: assume(not finicky) and any(x),
                settings=settings(database=database, timeout=5),
                database_key=key
            )
        except Unsatisfiable:
            pass
    stuff()
    assert len(set(database.fetch(key))) > 1
    finicky = True
    stuff()
    assert len(set(database.fetch(key))) == 0


def test_respects_max_examples_in_database_usage():
    key = b"a database key"
    database = SQLiteExampleDatabase(':memory:')
    do_we_care = True
    counter = [0]

    def check(x):
        counter[0] += 1
        return do_we_care and any(x)

    def stuff():
        try:
            find(
                st.binary(min_size=100), check,
                settings=settings(database=database, max_examples=10),
                database_key=key
            )
        except NoSuchExample:
            pass
    stuff()
    assert len(set(database.fetch(key))) > 10
    do_we_care = False
    counter[0] = 0
    stuff()
    assert counter == [10]


def test_clears_out_everything_smaller_than_the_interesting_example():
    in_clearing = False
    target = [None]

    for _ in range(5):
        # We retry the test run a few times to get a large enough initial
        # set of examples that we're not going to explore them all in the
        # initial run.
        cache = {}
        seen = set()

        database = InMemoryExampleDatabase()

        @settings(
            database=database, verbosity=Verbosity.quiet, max_examples=100)
        @given(st.binary(min_size=10, max_size=10))
        def test(i):
            if not in_clearing:
                if len([b for b in i if b > 1]) >= 8:
                    assert cache.setdefault(i, len(cache) % 10 != 9)
            elif len(seen) <= 20:
                seen.add(i)
            else:
                if target[0] is None:
                    remainder = sorted([s for s in saved if s not in seen])
                    target[0] = remainder[len(remainder) // 2]
                assert i in seen or i < target[0]

        with pytest.raises(AssertionError):
            test()

        saved, = database.data.values()
        if len(saved) > 30:
            break
    else:
        assert False, 'Never generated enough examples while shrinking'

    in_clearing = True

    with pytest.raises(AssertionError):
        test()

    saved, = database.data.values()

    for s in saved:
        assert s >= target[0]
