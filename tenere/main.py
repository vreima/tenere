import asyncio
import datetime
import math
import re
from collections.abc import Sequence
from contextlib import asynccontextmanager
from itertools import product
from typing import Protocol

import arrow
import motor.motor_asyncio
import telegram
from fastapi import FastAPI
from loguru import logger
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from tenere.config import settings


def to_float(value: str) -> float:
    try:
        return float(value.replace(",", ".").strip())
    except ValueError:
        return float("nan")


def filter_km(input: str) -> float:
    match = re.search(r"(\d+[,.]?\d*)\s*km", input, flags=re.IGNORECASE)

    if match:
        return to_float(match.group(1))

    return float("nan")


def filter_litres(input: str) -> float:
    match = re.search(r"(\d+[,.]?\d*)\s*[lL]", input, flags=re.IGNORECASE)

    if match:
        return to_float(match.group(1))
    return float("nan")


def filter_euros(input: str) -> float:
    match = re.search(r"(\d+[,.]?\d*)\s*[e|E|€]", input, flags=re.IGNORECASE)

    if match:
        return to_float(match.group(1))

    return float("nan")


def filter_datetime(input: str) -> datetime.datetime | None:
    date_formats = ["DD.MM.YYYY", "DD.M.YYYY", "D.MM.YYYY", "D.M.YYYY"]
    time_formats = ["HH:mm", "HH.mm", "HH:m", "HH.m", "H:mm", "H.mm", "H:m", "H.m"]

    for date_format, time_format in product(date_formats, time_formats):
        datetime_format = f"{date_format} {time_format}"
        try:
            return arrow.get(input, datetime_format, normalize_whitespace=True).datetime
        except arrow.parser.ParserError:
            continue

    for date_format in date_formats:
        try:
            return (
                arrow.get(input, date_format, normalize_whitespace=True)
                .shift(hours=12)
                .datetime
            )
        except arrow.parser.ParserError:
            continue

    return None


class DatabaseHandler:
    def __init__(self):
        self.client: motor.motor_asyncio.AsyncIOMotorClient = (
            motor.motor_asyncio.AsyncIOMotorClient(settings.mongo_url)
        )
        self.db = self.client["tenere_fuel"]
        self.collection = self.db["history"]

    async def write(self, document) -> str | None:
        logger.info(f"Inserting {document} into DB")

        await self.collection.insert_one(document)

        return "Tankattu {litres:.2f}L, {EUR:.2f}€ @ {km:.0f}km ({date}).".format(
            **document
        )


class SupportsHandlingJSON(Protocol):
    async def write(json) -> str | None:
        ...


class TelegramManager:
    def __init__(self, handlers: Sequence[SupportsHandlingJSON]):
        self.handlers = handlers

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!"
        )

    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(update.message.date)

        text = update.message.text
        km = filter_km(text)
        litres = filter_litres(text)
        euros = filter_euros(text)
        date = filter_datetime(text)

        logger.debug(update.message.chat)
        logger.debug(update.message.chat_id)

        if date is None:
            date = update.message.date

        if not all(map(math.isnan, (km, litres, euros))):
            if update.message.chat.type == telegram.Chat.GROUP:
                for handler in self.handlers:
                    result = handler.write(
                        {
                            "date": date,
                            "km": km,
                            "litres": litres,
                            "EUR": euros,
                        }
                    )

                    if result:
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id, text=result
                        )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"[DEBUG] Tankattu {litres:.2f}L, {euros:.2f}€ @ {km:.0f}km ({date}).",
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DatabaseHandler()
    manager = TelegramManager([db])

    async with ApplicationBuilder().token(
        settings.telegram_token
    ).build() as application:
        start_handler = CommandHandler("start", manager.start)
        application.add_handler(start_handler)
        echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), manager.echo)
        application.add_handler(echo_handler)

        await application.start()
        await application.updater.start_polling()
        yield
        await application.updater.stop()
        await application.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root() -> str:
    return "Hello, world!"


async def telegram_main():
    bot = telegram.Bot(settings.telegram_token)
    async with bot:
        while True:
            updates: list[Update] = await bot.get_updates()
            for u in updates:
                print(u.message.from_user, "::", u.message.text)
            await asyncio.sleep(2.0)
