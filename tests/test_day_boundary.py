import time

import pytest
from test_controller import dose

from kaa.domain import Refused, day_start


def test_dose_finishing_after_midnight_counts_in_current_day(rig):
    settings, store, _, _ = rig
    profile = store.profile("juniper-10")
    store.update_profile(profile["id"], {"dose_ml": 1, "daily_limit_ml": 1}, profile["revision"])
    store.arm()
    command = dose(store)
    store.claim()
    with store.db(True) as db:
        db.execute(
            "UPDATE commands SET created_at=? WHERE id=?",
            (
                day_start(time.time(), settings.timezone) - 1,
                command["id"],
            ),
        )
    store.finish(command["id"], "completed")
    assert store.snapshot()["plants"][0]["used_today_ml"] == 1
    with pytest.raises(Refused, match="daily_limit"):
        dose(store)
