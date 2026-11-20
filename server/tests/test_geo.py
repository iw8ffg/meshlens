from meshlens.geo import CountryLocator

loc = CountryLocator()


def test_inside():
    assert loc.locate(45.4642, 9.19) == "IT"  # Milano


def test_border_city():
    assert loc.locate(46.2044, 6.1432) == "CH"  # Ginevra


def test_sea_within_tolerance():
    assert loc.locate(43.75, 10.10) == "IT"  # ~10 km da Viareggio


def test_open_sea_is_none():
    assert loc.locate(39.5, 14.0) is None  # Tirreno meridionale, > 100 km dalla costa


def test_missing_or_zero():
    assert loc.locate(None, None) is None and loc.locate(0.0, 0.0) is None


def test_names():
    assert loc.names["IT"] in ("Italia", "Italy")
