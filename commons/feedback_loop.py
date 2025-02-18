import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Tuple

from bittensor.utils.btlogging import logging as logger

import dojo
from commons.orm import ORM
from commons.utils import datetime_as_utc
from database.prisma.models import MinerScore
from database.prisma.types import MinerScoreWhereInput
from dojo.protocol import DendriteQueryResponse, TaskSynapseObject


class FeedbackLoop:
    async def run(self):
        """Runs the feedback loop periodically."""
        while True:
            # Wait for the validator update score interval
            await asyncio.sleep(dojo.VALIDATOR_UPDATE_SCORE)
            try:
                result = await self.select_validator_task()
                if result:
                    task, completion = result
            except Exception as e:
                logger.error(f"Error in feedback loop: {e}")

    async def select_validator_task(self) -> Tuple[TaskSynapseObject, str] | None:
        """
        Selects a validator task from the latest expired tasks within a specific time window.
        Time window:
          - expire_from: current time minus 2 hours
          - expire_to: current time minus 1 hour
        Reason for using this time window:We want to select a task that has expired and been scored
        The task is only selected if there exists at least one completion where >50% and <90%
        of the miners scored it the highest.

        Returns:
            Tuple[TaskSynapseObject, str] | None: A tuple of (validator task, completion_id) if criteria are met;
        """
        expire_from = datetime_as_utc(datetime.now(timezone.utc)) - timedelta(hours=4)
        # TODO: Change back to 1 hour
        expire_to = datetime_as_utc(datetime.now(timezone.utc))

        eligible_tasks = []
        try:
            async for tasks_batch, has_more in ORM.get_expired_tasks(
                batch_size=10,
                expire_from=expire_from,
                expire_to=expire_to,
                is_processed=True,
            ):
                for dendrite_response in tasks_batch:
                    eligible_task = await self._evaluate_task(dendrite_response)
                    if eligible_task:
                        eligible_tasks.append(eligible_task)
        except Exception as e:
            logger.error(f"Error retrieving expired tasks: {e}")
            return None

        if not eligible_tasks:
            logger.info("No tasks meeting criteria found.")
            return None

        selected_task, selected_completion = random.choice(eligible_tasks)
        logger.info(
            f"Selected validator task with ID: {selected_task.task_id} and completion ID: {selected_completion}"
        )
        return selected_task, selected_completion

    async def _evaluate_task(
        self, dendrite_response: DendriteQueryResponse
    ) -> Tuple[TaskSynapseObject, str] | None:
        """
        Evaluates a single task based on its miner scores from the MinerScore table.
        For each completion in the task, computes what percentage of miners scored it
        highest based on raw_score. If any completion has >50% and <90% of miners
        scoring it the highest, then the task qualifies.

        Args:
            dendrite_response (DendriteQueryResponse): Contains the validator task and related miner responses.

        Returns:
            Optional[Tuple[TaskSynapseObject, str]]: Tuple of (validator task, completion_id) if criteria are met;
            otherwise None.
        """
        validator_task: TaskSynapseObject = dendrite_response.validator_task

        if not validator_task.task_id:
            logger.debug("Task ID is missing")
            return None

        try:
            # Get all miner scores for this validator task
            miner_scores = await MinerScore.prisma().find_many(
                where=MinerScoreWhereInput(
                    {
                        "miner_response_relation": {
                            "is": {"validator_task_id": validator_task.task_id}
                        }
                    }
                ),
                include={
                    "criterion_relation": {"include": {"completion_relation": True}},
                    "miner_response_relation": True,
                },
            )

            if not miner_scores:
                logger.debug(f"No miner scores found for task {validator_task.task_id}")
                return None

            # Group scores by miner response ID and completion ID
            # map of miner_response_id -> completion_id
            miner_best_completions = {}
            # map of completion_id -> list of miners and their raw scores
            completion_scores = {}

            for score in miner_scores:
                if (
                    not score.scores
                    or not score.criterion_relation
                    or not score.criterion_relation.completion_relation
                ):
                    continue

                # Parse the scores JSON
                scores_dict = json.loads(score.scores)
                miner_raw_score = scores_dict.get("raw_score")
                if miner_raw_score is None:
                    continue

                completion_id = (
                    score.criterion_relation.completion_relation.completion_id
                )
                miner_response_id = score.miner_response_id

                # Store score for this completion
                if completion_id not in completion_scores:
                    completion_scores[completion_id] = []
                completion_scores[completion_id].append(
                    (miner_response_id, miner_raw_score)
                )

            # Find highest scored completion for each miner
            for completion_id, scores in completion_scores.items():
                for miner_response_id, score in scores:
                    current_best = miner_best_completions.get(miner_response_id)
                    if (
                        current_best is None
                        or score > completion_scores[current_best][0][1]
                    ):
                        miner_best_completions[miner_response_id] = completion_id

            total_miners = len(set(miner_best_completions.keys()))
            if total_miners == 0:
                return None

            # Count how many miners scored each completion as best
            completion_counts = {}
            for best_completion in miner_best_completions.values():
                completion_counts[best_completion] = (
                    completion_counts.get(best_completion, 0) + 1
                )

            # Check percentages for each completion
            for completion_id, count in completion_counts.items():
                percentage = (count / total_miners) * 100
                # TODO: Change back to < 90
                if 50 < percentage < 101:
                    logger.info(
                        f"Found eligible completion {completion_id} with {percentage:.1f}% "
                        f"of miners ({count}/{total_miners}) scoring it highest"
                    )
                    return validator_task, completion_id

            return None

        except Exception as e:
            logger.error(f"Error evaluating task {validator_task.task_id}: {e}")
            return None
