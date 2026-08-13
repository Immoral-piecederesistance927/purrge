from purrge import awake


def test_enable_disable_tracks_state():
    awake.enable()
    assert awake.is_active()
    awake.disable()
    assert not awake.is_active()
