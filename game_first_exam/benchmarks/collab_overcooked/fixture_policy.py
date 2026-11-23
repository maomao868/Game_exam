"""Deterministic boiled-egg responses used only by the offline integration test."""
def choose(role, messages):
    prompt = messages[-1]["content"]
    head, _, scene = prompt.partition("<input>\n")
    has_recipe = "Place the egg in the pot and cook for 3 timesteps" in head
    assert has_recipe == (role == "Chef"), f"Incorrect recipe visibility for {role}"
    assert f"Suppose you are a {role}" in head
    say = "[NOTHING]"
    if role == "Assistant":
        if "egg" in scene and "place_obj_on_counter()" not in scene.split("Order:")[0]:
            plan = "pickup(egg,ingredient_dispenser);place_obj_on_counter()"
        else:
            plan = "wait(3)"
    elif "Scene 0:" in scene and "say history" not in scene:
        plan = "request(pickup(egg,ingredient_dispenser));request(place_obj_on_counter());wait(3)"
        say = "Please put an egg on the counter. [END]"
    elif "<Chef> holds boiled_egg" in scene:
        plan = "deliver_soup()"
    elif "<pot0> has boiled_egg" in scene:
        plan = "pickup(boiled_egg,pot0);deliver_soup()"
    elif "<pot0> starts processing" in scene:
        plan = "wait(1)"
    else:
        plan = "pickup(egg,counter);put_obj_in_utensil(pot0);cook(pot0);wait(3);pickup(boiled_egg,pot0);deliver_soup()"
    return f"{role} analysis: Follow the current order.\n{role} plan: {plan}\n{role} say: {say}", 0
