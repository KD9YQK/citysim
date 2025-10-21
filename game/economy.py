from .resources_base import add_resources


def calculate_resources_per_tick(player_id):
    tick_income = {"food": 3, "wood": 1}
    add_resources(player_id, tick_income)
