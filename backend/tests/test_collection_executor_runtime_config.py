from modules.apps.collection_center import executor_v2


def test_runtime_task_params_include_time_selection_and_range_fields_for_preset():
    normalized_date_range = {
        "start_date": "2026-03-08",
        "end_date": "2026-03-14",
        "date_from": "2026-03-08",
        "date_to": "2026-03-14",
        "time_selection": {
            "mode": "preset",
            "preset": "last_7_days",
        },
    }

    params = executor_v2._build_runtime_task_params(
        task_id="task-1",
        account={"account_id": "acc-1"},
        platform="miaoshou",
        granularity="weekly",
        normalized_date_range=normalized_date_range,
        task_download_dir="temp/downloads/task-1",
        screenshot_dir="temp/screenshots/task-1",
        reused_session=False,
    )

    assert params["time_selection"] == {"mode": "preset", "preset": "last_7_days"}
    assert params["start_date"] == "2026-03-08"
    assert params["end_date"] == "2026-03-14"
    assert params["params"]["date_from"] == "2026-03-08"
    assert params["params"]["date_to"] == "2026-03-14"


def test_runtime_task_params_include_custom_date_range_for_custom_selection():
    normalized_date_range = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-07",
        "date_from": "2026-03-01",
        "date_to": "2026-03-07",
        "time_selection": {
            "mode": "custom",
            "start_date": "2026-03-01",
            "end_date": "2026-03-07",
            "start_time": "00:00:00",
            "end_time": "23:59:59",
        },
    }

    params = executor_v2._build_runtime_task_params(
        task_id="task-2",
        account={"account_id": "acc-2"},
        platform="miaoshou",
        granularity="daily",
        normalized_date_range=normalized_date_range,
        task_download_dir="temp/downloads/task-2",
        screenshot_dir="temp/screenshots/task-2",
        reused_session=True,
    )

    assert params["time_selection"]["mode"] == "custom"
    assert params["custom_date_range"] == {
        "start_date": "2026-03-01",
        "end_date": "2026-03-07",
        "start_time": "00:00:00",
        "end_time": "23:59:59",
    }


def test_runtime_task_params_keep_top_level_granularity_for_shopee_custom_date_components():
    normalized_date_range = {
        "start_date": "2026-03-01",
        "end_date": "2026-03-31",
        "date_from": "2026-03-01",
        "date_to": "2026-03-31",
        "time_selection": {
            "mode": "custom",
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
            "start_time": "00:00:00",
            "end_time": "23:59:59",
        },
    }

    params = executor_v2._build_runtime_task_params(
        task_id="task-3",
        account={"account_id": "acc-3"},
        platform="shopee",
        granularity="monthly",
        normalized_date_range=normalized_date_range,
        task_download_dir="temp/downloads/task-3",
        screenshot_dir="temp/screenshots/task-3",
        reused_session=False,
    )

    assert params["granularity"] == "monthly"
    assert params["params"]["granularity"] == "monthly"
