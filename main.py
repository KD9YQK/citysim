import asyncio
from game.utils import load_config
from game.db import Database
from game.models import init as models_init
from game.telnet_server import start_server


def prepare():
    cfg = load_config()
    db_path = cfg.get('db_path', 'city_sim.db')
    # ensure DB instance
    Database.instance(db_path)
    models_init(db_path)


if __name__ == '__main__':
    prepare()
    game_cfg = load_config()
    try:
        asyncio.run(start_server(game_cfg))
    except KeyboardInterrupt:
        print('Shutting down...')
