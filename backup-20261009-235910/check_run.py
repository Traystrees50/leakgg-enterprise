import sys
import logging
sys.path.insert(0, '.')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True
)

root = logging.getLogger()
print(f'Root handlers: {len(root.handlers)}', flush=True)

import discord
from discord.ext import commands
import inspect

sig = inspect.signature(commands.Bot.run)
print(f'Bot.run signature: {sig}', flush=True)

default_val = sig.parameters["log_handler"].default
print(f'log_handler default: {default_val}', flush=True)
print(f'log_handler default is None: {default_val is None}', flush=True)

from discord.utils import MISSING
print(f'MISSING: {MISSING}', flush=True)
print(f'MISSING is None: {MISSING is None}', flush=True)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
print(f'Root handlers after Bot init: {len(root.handlers)}', flush=True)
