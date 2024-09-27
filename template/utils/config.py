import argparse
import os
from pathlib import Path

import bittensor as bt
from loguru import logger

logger_name = "named_logger"


def monkeypatch():
    """Monkeypatches the logger to add a name attribute."""
    import loguru

    patched_logger = loguru.logger.bind(name=logger_name)
    loguru.logger = patched_logger


monkeypatch()


base_path = Path.cwd()


def check_config(config: bt.config):
    """Checks/validates the config namespace object."""
    # logger.check_config(config)

    log_dir = str(base_path / "logs")
    full_path = os.path.expanduser(
        f"{log_dir}/{config.wallet.name}/{config.wallet.hotkey}/netuid{config.netuid}/{config.neuron.name}"
    )
    config.neuron.full_path = os.path.expanduser(full_path)
    if not os.path.exists(config.neuron.full_path):
        os.makedirs(config.neuron.full_path, exist_ok=True)

    bt.logging.enable_third_party_loggers()


def add_args(parser):
    from template.protocol import ScoringMethod

    """
    Adds relevant arguments to the parser for operation.
    """
    # Netuid Arg: The netuid of the subnet to connect to.
    parser.add_argument("--netuid", type=int, help="Subnet netuid", default=1)

    import sys

    args, _ = parser.parse_known_args()
    debug: str = vars(args).get("logging.debug")
    trace: str = vars(args).get("logging.trace")
    info: str = vars(args).get("logging.info")

    if trace:
        logger.remove()
        logger.add(sys.stdout, level="TRACE", colorize=True)
    elif debug:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG", colorize=True)
    elif info:
        logger.remove()
        logger.add(sys.stdout, level="INFO", colorize=True)
    else:
        logger.remove()
        logger.add(sys.stdout, level="INFO", colorize=True)

    logger.add(
        sys.stderr,
        level="ERROR",  # Only send ERROR and above to stderr
    )

    neuron_types = ["miner", "validator"]
    parser.add_argument(
        "--neuron.type",
        choices=neuron_types,
        type=str,
        help="Whether running a miner or validator",
    )
    args, unknown = parser.parse_known_args()
    neuron_type = None
    if known_args := vars(args):
        neuron_type = known_args["neuron.type"]

    parser.add_argument(
        "--neuron.name",
        type=str,
        help="Trials for this neuron go in neuron.root / (wallet_cold - wallet_hot) / neuron.name. ",
        default=neuron_type,
    )

    # device = get_device()
    parser.add_argument(
        "--neuron.device", type=str, help="Device to run on.", default="cpu"
    )

    parser.add_argument(
        "--neuron.epoch_length",
        type=int,
        help="The default epoch length (how often we set weights, measured in 12 second blocks).",
        default=100,
    )

    parser.add_argument(
        "--api.port",
        type=int,
        help="FastAPI port for uvicorn to run on, should be different from axon.port as these will serve external requests.",
        default=1888,
    )

    if neuron_type == "validator":
        parser.add_argument(
            "--data_manager.base_path",
            type=str,
            help="Base path to store data to.",
            default=base_path,
        )

        parser.add_argument(
            "--neuron.sample_size",
            type=int,
            help="The number of miners to query per dendrite call.",
            default=10,
        )

        parser.add_argument(
            "--neuron.moving_average_alpha",
            type=float,
            help="Moving average alpha parameter, how much to add of the new observation.",
            default=0.3,
        )

        wandb_project_names = ["dojo-devnet", "dojo-testnet", "dojo-mainnet"]
        parser.add_argument(
            "--wandb.project_name",
            type=str,
            choices=wandb_project_names,
            help="Name of the wandb project to use.",
        )

    elif neuron_type == "miner":
        parser.add_argument(
            "--scoring_method",
            help="Method to use for scoring completions.",
            choices=[str(method) for method in ScoringMethod],
        )


def get_config():
    """Returns the configuration object specific to this miner or validator after adding relevant arguments."""
    parser = argparse.ArgumentParser()
    bt.wallet.add_args(parser)
    bt.logging.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.axon.add_args(parser)
    add_args(parser)
    _config = bt.config(parser)

    check_config(_config)
    return _config
