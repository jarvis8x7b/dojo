import functools
import os
from typing import List

import aiohttp
from commons.utils import log_retry_info
from dotenv import load_dotenv
from loguru import logger
from template.protocol import SyntheticQA
from tenacity import AsyncRetrying, RetryError, stop_after_attempt

load_dotenv()


SYNTHETIC_API_BASE_URL = os.getenv("SYNTHETIC_API_URL")


@functools.lru_cache
def get_client_session():
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))


class SyntheticAPI:
    @classmethod
    async def get_qa(cls) -> List[SyntheticQA]:
        path = f"{SYNTHETIC_API_BASE_URL}/api/synthetic-gen"
        logger.debug(f"Generating synthetic QA from {path}.")
        # Instantiate the aiohttp ClientSession outside the loop

        session = get_client_session()
        MAX_RETRIES = 3
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(MAX_RETRIES), before_sleep=log_retry_info
            ):
                with attempt:
                    async with session.get(path) as response:
                        response.raise_for_status()
                        response_json = await response.json()
                        if "body" not in response_json:
                            raise ValueError("Invalid response from the server.")
                        synthetic_qa = SyntheticQA.parse_obj(response_json["body"])
                        logger.info("Synthetic QA generated and parsed successfully.")
                        return synthetic_qa
        except RetryError:
            logger.error("Failed to generate synthetic QA after retries.")
            return None