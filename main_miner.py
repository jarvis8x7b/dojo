import asyncio

import wandb
from bittensor.btlogging import logging as logger

from commons.objects import ObjectManager
from template.utils.config import source_dotenv

source_dotenv()

miner = ObjectManager.get_miner()


async def shutdown():
    """Asynchronously cleanup tasks tied to the service's shutdown."""
    logger.info("Received exit signal, shutting down asynchronously...")
    miner._should_exit = True
    await asyncio.sleep(1)  # Simulate some async cleanup
    wandb.finish()


async def main():
    log_task = asyncio.create_task(miner.log_miner_status())
    run_task = asyncio.create_task(miner.run())

    await asyncio.gather(log_task, run_task)
    logger.info("Exiting main function.")


if __name__ == "__main__":
    asyncio.run(main())
