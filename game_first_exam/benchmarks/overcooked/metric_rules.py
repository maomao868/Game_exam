"""Check the trusted native team return and episode boundary."""


def validate_metrics(final, instance):
    metrics = final["metrics"]
    steps = metrics["native_steps"]
    if type(steps) is not int or steps != final["steps"] or not 0 <= steps <= instance["horizon"]:
        raise ValueError("invalid native kitchen step count")
    if type(metrics["deliveries"]) is not int or not 0 <= metrics["deliveries"] <= 2 * steps:
        raise ValueError("invalid delivery count")
    reward = metrics["native_return"]
    if type(reward) not in (int, float) or reward < 0 or reward != final["return"]:
        raise ValueError("native kitchen return disagrees with the service")
    completed = steps == instance["horizon"]
    if final["terminated"] or final["truncated"] != completed or final["success"] != completed:
        raise ValueError("native kitchen horizon disagrees with final flags")
