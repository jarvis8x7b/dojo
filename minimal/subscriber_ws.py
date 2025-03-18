import asyncio
import json

import websockets
from substrateinterface import SubstrateInterface

url = "wss://entrypoint-finney.opentensor.ai:443"
substrate = SubstrateInterface(url=url)

# Get the current finalized block hash
finalized_hash = substrate.get_chain_finalised_head()
print("Finalized block hash:", finalized_hash)

# Get the current finalized block number
finalized_block = substrate.get_block_number(finalized_hash)
print("Finalized block number:", finalized_block)


# Check if a specific block number is finalized
def is_block_finalized(block_number):
    finalized_hash = substrate.get_chain_finalised_head()
    finalized_block = substrate.get_block_number(finalized_hash)
    return block_number <= finalized_block


async def subscribe_to_blocks(node_url):
    while True:
        try:
            async with websockets.connect(node_url) as websocket:
                # Subscribe to new blocks
                await websocket.send(
                    json.dumps(
                        {
                            "id": 1,
                            "jsonrpc": "2.0",
                            "method": "chain_subscribeFinalizedHeads",
                            "params": [],
                        }
                    )
                )

                # Get subscription ID
                response = await websocket.recv()
                subscription_id = json.loads(response)["result"]

                # Process incoming blocks
                while True:
                    response = await websocket.recv()
                    data = json.loads(response)
                    print(data)
                    if (
                        "params" in data
                        and data["params"]["subscription"] == subscription_id
                    ):
                        block_header = data["params"]["result"]
                        block_number = int(block_header["number"], 16)
                        print(f"New block #{block_number}")
                        if is_block_finalized(block_number):
                            print(f"Block #{block_number} is finalized")
                        else:
                            print(f"Block #{block_number} is not finalized")
                        # Process the block...
        except (websockets.ConnectionClosed, asyncio.CancelledError) as e:
            print(f"Connection closed: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"An error occurred: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


asyncio.run(subscribe_to_blocks(url))
