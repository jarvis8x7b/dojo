package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strconv"
	"time"

	"github.com/gorilla/websocket"
)

const url = "wss://entrypoint-finney.opentensor.ai:443"

// RPC request structure
type rpcRequest struct {
	ID      int           `json:"id"`
	JSONRPC string        `json:"jsonrpc"`
	Method  string        `json:"method"`
	Params  []interface{} `json:"params"`
}

// RPC response structure
type rpcResponse struct {
	ID      int             `json:"id"`
	JSONRPC string          `json:"jsonrpc"`
	Result  json.RawMessage `json:"result"`
	Error   *rpcError       `json:"error,omitempty"`
}

// RPC subscription response
type subscriptionResponse struct {
	JSONRPC string             `json:"jsonrpc"`
	Method  string             `json:"method"`
	Params  subscriptionParams `json:"params"`
}

type subscriptionParams struct {
	Subscription string          `json:"subscription"`
	Result       json.RawMessage `json:"result"`
}

// RPC error structure
type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// BlockHeader represents a simplified Substrate block header
type BlockHeader struct {
	Number string `json:"number"`
	// Other fields omitted for brevity
}

// SubstrateClient handles interactions with a Substrate node
type SubstrateClient struct {
	url string
}

// NewSubstrateClient creates a new client for the given URL
func NewSubstrateClient(url string) *SubstrateClient {
	return &SubstrateClient{url: url}
}

func (s *SubstrateClient) getChainFinalizedHead() (string, error) {
	conn, err := s.connectWebSocket()
	if err != nil {
		return "", err
	}
	defer conn.Close()

	request := rpcRequest{
		ID:      1,
		JSONRPC: "2.0",
		Method:  "chain_getFinalizedHead",
		Params:  []interface{}{},
	}

	err = conn.WriteJSON(request)
	if err != nil {
		return "", fmt.Errorf("write error: %w", err)
	}

	var response rpcResponse
	err = s.readWebSocketResponse(conn, &response)
	if err != nil {
		return "", err
	}

	if response.Error != nil {
		return "", fmt.Errorf("RPC error: %s", response.Error.Message)
	}

	var blockHash string
	err = json.Unmarshal(response.Result, &blockHash)
	if err != nil {
		return "", fmt.Errorf("unmarshal error: %w", err)
	}

	return blockHash, nil
}

func (s *SubstrateClient) getBlockNumber(blockHash string) (uint64, error) {
	conn, err := s.connectWebSocket()
	if err != nil {
		return 0, err
	}
	defer conn.Close()

	request := rpcRequest{
		ID:      1,
		JSONRPC: "2.0",
		Method:  "chain_getHeader",
		Params:  []interface{}{blockHash},
	}

	err = conn.WriteJSON(request)
	if err != nil {
		return 0, fmt.Errorf("write error: %w", err)
	}

	var response rpcResponse
	err = s.readWebSocketResponse(conn, &response)
	if err != nil {
		return 0, err
	}

	if response.Error != nil {
		return 0, fmt.Errorf("RPC error: %s", response.Error.Message)
	}

	var header BlockHeader
	err = json.Unmarshal(response.Result, &header)
	if err != nil {
		return 0, fmt.Errorf("unmarshal error: %w", err)
	}

	log.Printf("Header: %+v", header)

	blockNum, err := strconv.ParseUint(header.Number[2:], 16, 64)
	if err != nil {
		return 0, fmt.Errorf("parse error: %w", err)
	}

	return blockNum, nil
}

func (s *SubstrateClient) connectWebSocket() (*websocket.Conn, error) {
	conn, _, err := websocket.DefaultDialer.Dial(s.url, nil)
	if err != nil {
		return nil, fmt.Errorf("dial error: %w", err)
	}
	return conn, nil
}

func (s *SubstrateClient) readWebSocketResponse(conn *websocket.Conn, response *rpcResponse) error {
	err := conn.ReadJSON(response)
	if err != nil {
		return fmt.Errorf("read error: %w", err)
	}
	return nil
}

// isBlockFinalized checks if a block number is finalized
func (s *SubstrateClient) isBlockFinalized(blockNumber uint64) (bool, error) {
	finalizedHash, err := s.getChainFinalizedHead()
	if err != nil {
		return false, err
	}

	finalizedBlock, err := s.getBlockNumber(finalizedHash)
	if err != nil {
		return false, err
	}

	return blockNumber <= finalizedBlock, nil
}

func (s *SubstrateClient) subscribeToBlocks(ctx context.Context) {
	for {
		conn, err := s.connectWebSocket()
		if err != nil {
			log.Printf("Connection error: %v. Reconnecting in 5 seconds...", err)
			select {
			case <-time.After(5 * time.Second):
				continue
			case <-ctx.Done():
				return
			}
		}

		err = s.subscribe(ctx, conn)
		if err != nil {
			log.Printf("Subscription error: %v. Reconnecting in 5 seconds...", err)
			select {
			case <-time.After(5 * time.Second):
				continue
			case <-ctx.Done():
				return
			}
		}
	}
}

func (s *SubstrateClient) subscribe(ctx context.Context, conn *websocket.Conn) error {
	defer conn.Close()

	// Subscribe to finalized heads
	request := rpcRequest{
		ID:      1,
		JSONRPC: "2.0",
		Method:  "chain_subscribeFinalizedHeads",
		Params:  []interface{}{},
	}

	err := conn.WriteJSON(request)
	if err != nil {
		return fmt.Errorf("write error: %w", err)
	}

	// Get subscription ID
	var response rpcResponse
	err = conn.ReadJSON(&response)
	if err != nil {
		return fmt.Errorf("read error: %w", err)
	}

	if response.Error != nil {
		return fmt.Errorf("RPC error: %s", response.Error.Message)
	}

	var subscriptionID string
	err = json.Unmarshal(response.Result, &subscriptionID)
	if err != nil {
		return fmt.Errorf("unmarshal error: %w", err)
	}

	// Process incoming blocks
	for {
		select {
		case <-ctx.Done():
			return nil
		default:
			// Set read deadline to avoid blocking forever
			err = conn.SetReadDeadline(time.Now().Add(10 * time.Second))
			if err != nil {
				return fmt.Errorf("set deadline error: %w", err)
			}

			var subResponse subscriptionResponse
			err = conn.ReadJSON(&subResponse)
			if err != nil {
				return fmt.Errorf("read error: %w", err)
			}

			var blockHeader BlockHeader
			err = json.Unmarshal(subResponse.Params.Result, &blockHeader)
			if err != nil {
				return fmt.Errorf("unmarshal error: %w", err)
			}

			blockNum, err := strconv.ParseUint(blockHeader.Number[2:], 16, 64)
			if err != nil {
				return fmt.Errorf("parse error: %w", err)
			}

			fmt.Printf("New block #%d at %s\n", blockNum, time.Now().Format(time.RFC3339))

			// Check if block is finalized
			isFinalized, err := s.isBlockFinalized(blockNum)
			if err != nil {
				log.Printf("Error checking if block is finalized: %v", err)
			} else if isFinalized {
				fmt.Printf("Block #%d is finalized\n", blockNum)
			} else {
				fmt.Printf("Block #%d is not finalized\n", blockNum)
			}

			// Process the block...
		}
	}
}

func main() {
	// Create a new Substrate client
	substrate := NewSubstrateClient(url)

	// Get the current finalized block hash
	finalizedHash, err := substrate.getChainFinalizedHead()
	if err != nil {
		log.Fatalf("Error getting finalized head: %v", err)
	}
	fmt.Println("Finalized block hash:", finalizedHash)

	// Get the current finalized block number
	finalizedBlock, err := substrate.getBlockNumber(finalizedHash)
	if err != nil {
		log.Fatalf("Error getting block number: %v", err)
	}
	fmt.Println("Finalized block number:", finalizedBlock)

	// Create a context that can be canceled
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Subscribe to blocks
	substrate.subscribeToBlocks(ctx)
}
