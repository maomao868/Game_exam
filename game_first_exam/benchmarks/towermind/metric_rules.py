"""Validate native outcome evidence without loading Unity."""
def validate_metrics(final, instance):
    metrics = final["metrics"]
    health = metrics["base_health"]
    if type(health) is not int or health < 0:
        raise ValueError("invalid TowerMind base health")
    if type(metrics["native_decisions"]) is not int or metrics["native_decisions"] != final["steps"]:
        raise ValueError("TowerMind decision count disagrees with the service")
    reward = metrics["native_return"]
    if type(reward) not in (int, float) or reward != final["return"]:
        raise ValueError("TowerMind cumulative return disagrees with the service")
    counted, invalid = metrics["native_counted_actions"], metrics["native_invalid_actions"]
    if type(counted) is not int or type(invalid) is not int or not 0 <= invalid <= counted <= final["steps"]:
        raise ValueError("invalid TowerMind action counts")
    won = final["reason"] == "native_terminated" and health > 0
    if final["success"] != won:
        raise ValueError("TowerMind success requires a completed native level with the base alive")
