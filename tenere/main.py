import datetime
import math
import re
from contextlib import asynccontextmanager
from functools import partial
from itertools import product
from typing import Self

import arrow
import motor.motor_asyncio
from fastapi import FastAPI
from loguru import logger
from pydantic import BaseModel
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
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


def filter_suffixed_value(text: str, suffix_regex: str) -> float:
    match = re.search(
        rf"([+-]?\d+[,.]?\d*)\s*{suffix_regex}", text, flags=re.IGNORECASE
    )

    if match:
        return to_float(match.group(1))

    return float("nan")


filter_km = partial(filter_suffixed_value, suffix_regex="km")
filter_litres = partial(filter_suffixed_value, suffix_regex="[lL]")
filter_euros = partial(filter_suffixed_value, suffix_regex="[e|E|€]")


def filter_datetime(text: str) -> datetime.datetime | None:
    date_formats = ["DD.MM.YYYY", "DD.M.YYYY", "D.MM.YYYY", "D.M.YYYY"]
    time_formats = ["HH:mm", "HH.mm", "HH:m", "HH.m", "H:mm", "H.mm", "H:m", "H.m"]

    datetime_formats = [
        f"{date_format} {time_format}"
        for date_format, time_format in product(date_formats, time_formats)
    ]
    try:
        return arrow.get(
            text, datetime_formats, normalize_whitespace=True, tzinfo="Europe/Helsinki"
        ).datetime
    except (arrow.parser.ParserError, ValueError):
        pass

    try:
        return arrow.get(
            text, date_formats, normalize_whitespace=True, tzinfo="Europe/Helsinki"
        ).datetime
    except (arrow.parser.ParserError, ValueError):
        return None


class FuelingInputModel(BaseModel):
    date: datetime.datetime
    fuel_litres: float
    distance_km: float
    cost_euros: float

    @classmethod
    def from_text(cls, text: str, default_date: datetime.datetime) -> Self:
        """
        Create a fueling metric instance from free-form text, for example
        'fueled 10.8 L, 22.05 €, odometer at 11782 km'.
        """
        date = filter_datetime(text) or default_date
        fuel = filter_litres(text)
        distance = filter_km(text)
        cost = filter_euros(text)

        return cls(date=date, fuel_litres=fuel, distance_km=distance, cost_euros=cost)

    def __bool__(self) -> bool:
        """
        Return False if this fueling input instance is empty, ie. if all the metrics are nan.
        """
        return not (
            math.isnan(self.fuel_litres)
            and math.isnan(self.distance_km)
            and math.isnan(self.cost_euros)
        )

    def __str__(self) -> str:
        return f"{self.fuel_litres:.2f}L {self.cost_euros:.2f}€ {self.distance_km:.0f}km @ {self.date}"


class DatabaseHandler:
    def __init__(self):
        self.client: motor.motor_asyncio.AsyncIOMotorClient = (
            motor.motor_asyncio.AsyncIOMotorClient(settings.mongo_url)
        )
        self.db = self.client[settings.database]
        self.collection = self.db[settings.collection]

    async def write(self, document: FuelingInputModel) -> None:
        logger.info(f"Inserting {document} into DB")

        await self.collection.insert_one(document.model_dump())


async def message_to_database(
    update: Update, context: ContextTypes.DEFAULT_TYPE, db: DatabaseHandler
) -> None:
    if update.message is None or update.effective_chat is None:
        logger.error(f"Message is empty: {update=}")
        return

    logger.debug(update.effective_chat)

    text: str = update.message.text or ""
    fueled = FuelingInputModel.from_text(text, update.message.date)
    if fueled:
        await db.write(fueled)
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=f"Tankattu {fueled}"
        )


async def message_echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        logger.error(f"Message is empty: {update=}")
        return

    logger.debug(update.effective_chat)

    text: str = update.message.text or ""
    fueled = FuelingInputModel.from_text(text, update.message.date)
    if fueled:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, text=f"(Debug) Tankattu {fueled}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    db = DatabaseHandler()

    async with ApplicationBuilder().token(
        settings.telegram_token
    ).build() as application:
        # start_handler = CommandHandler("start", manager.start)
        # application.add_handler(start_handler)

        production_msg_handler = MessageHandler(
            filters.TEXT
            & (~filters.COMMAND)
            & filters.Chat(settings.production_chat_id),
            partial(message_to_database, db=db),
        )
        application.add_handler(production_msg_handler)

        debug_msg_handler = MessageHandler(
            filters.TEXT
            & (~filters.COMMAND)
            & (~filters.Chat(settings.production_chat_id)),
            message_echo,
        )
        application.add_handler(debug_msg_handler)

        await application.start()
        await application.updater.start_polling()  # type: ignore
        yield
        await application.updater.stop()  # type: ignore
        await application.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root() -> str:
    return "Hello, world!"
