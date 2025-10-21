# lore.py
import random
from .utils import load_config
from .events import send_message


def get_random_lore():
    try:
        lore_list = load_config("lore.yaml")
        if isinstance(lore_list, list) and lore_list:
            return random.choice(lore_list)
        return None
    except Exception:
        return None


def send_lore_to_player(player):
    lore = get_random_lore()
    if lore:
        send_message(player, f"Lore: {lore}")
